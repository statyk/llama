# Spec-compliance verdict — Tasks 3 / 4 / 4b (usage-pacing phase 1)

Reviewer: spec-compliance (independent). Read-only; no edits, no commits.
Range: `4b5a2d2..682240d` (`e4c0786`, `cb0b5ff`, `682240d`) on `usage-pacing`.
Authority: `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`
("herder changes", "Integration", "Testing") above the three briefs.

## Verdict

**Spec verdict: ✅ APPROVED (batch)**

- Task 3 (`claude_cli` raises `RateLimited` + captures raw output): ✅
- Task 4 (`_with_transport_retry` no-retry set): ✅
- Task 4b (`gather` re-raises ahead of the broad clause): ✅

The invariant the batch exists to establish — *a usage-window refusal is neither
swallowed nor retried* — holds end to end on the `claude_cli` backend, from
`_run` through `run_json_task`/`run_research_task`, through `run_gather`'s
`align_structure` fallback, to `_execute`. The only remaining `except HerderError`
on that path is `cli.py:237`, which is the next task by design.

No blocking findings. Six Minor observations, three of which are spec-text or
future-task notes rather than defects in this diff.

---

## Requirement-by-requirement

### Task 3 — raise `RateLimited` from the `claude_cli` provider

| # | Requirement | Where met | Note |
|---|---|---|---|
| 3.1 | Import `capture_failure` and `classify` | `packages/herder/src/herder/claude_cli.py:9-10` | Literal per brief. Module-level, above `from herder.provider import HerderError`. |
| 3.2 | Non-zero-exit branch: message → capture → classify → raise | `claude_cli.py:128-133` | Byte-equivalent to the brief's snippet. |
| 3.3 | JSON-decode branch: capture, then plain `HerderError` | `claude_cli.py:136-138` | Per brief (capture only, no classify). |
| 3.4 | `is_error` envelope branch: message → capture → classify → raise | `claude_cli.py:140-145` | Byte-equivalent to the brief's snippet. |
| 3.5 | Test: session limit on non-zero exit → `RateLimited`, `scope == "five_hour"` | `packages/herder/tests/test_claude_cli.py:222-227` | Verbatim from brief. |
| 3.6 | Test: session limit inside an error envelope → `RateLimited` | `test_claude_cli.py:229-234` | Verbatim. |
| 3.7 | Test: dropped connection stays a plain `HerderError` (the negative set the spec's Testing section calls load-bearing) | `test_claude_cli.py:236-241` | Uses the existing `CLOSED_MID` fixture (`test_claude_cli.py:138-146`), exactly as the spec requires. `assert not isinstance(exc.value, RateLimited)`. |
| 3.8 | Test: a failure is captured when a capture dir is set | `test_claude_cli.py:243-257` | Verbatim; `tmp_path`, reset in `finally`. |
| 3.9 | Spec: positive fixture carries the measured string **with a literal U+00B7** | `test_claude_cli.py:220-221` | **Verified byte-wise**: the separator is `0xB7` (U+00B7 MIDDLE DOT), not U+2022. The assembled message is `claude exited 1: You've hit your session limit · resets 11:10am (America/New_York)` — the spec's verbatim positive fixture. |
| 3.10 | Spec: `RateLimited` raised from `claude_cli._run`'s *existing* failure paths | `claude_cli.py:128-145` | Both realistic paths covered. Two paths remain unclassified — see Finding M1. |

### Task 4 — stop retrying a rate limit as transport noise

| # | Requirement | Where met | Note |
|---|---|---|---|
| 4.1 | `from herder.limits import RateLimited` | `packages/herder/src/herder/tasks.py:7` | Deep import, not via `herder/__init__.py` — avoids the import cycle (`limits.py:21` imports `HerderError` straight from `herder.provider`). Correct and per brief. |
| 4.2 | `RateLimited` joins the no-retry tuple (spec: "at `tasks.py:36`") | `tasks.py:40` | `except (TaskFailed, ResearchNotSupported, RateLimited): raise`. Line moved by the docstring growth; the construct is exactly as specified. |
| 4.3 | Docstring extended with the reason | `tasks.py:31-34` | Brief's final paragraph, verbatim. |
| 4.4 | Test: not retried, no backoff slept | `packages/herder/tests/test_llm_tasks.py:203-213` | Verbatim; `assert provider.calls == 1` **and** `assert slept == []`. |
| 4.5 | Test: propagates from a research task | `test_llm_tasks.py:216-221` | Verbatim; covers the `run_research_task` seam too. |
| 4.6 | `CountingLimitProvider` reuses the file's existing `Answer`/`tasks` imports | `test_llm_tasks.py:191-201` | Confirmed: only `RateLimited` added. |
| 4.7 | No other retry/escalation layer re-enters | `tasks.py:93-103`, `tasks.py:122-133` | **Independently checked**: neither `run_json_task` nor `run_research_task` catches `HerderError`, so the ladder never escalates a tier on a limit hit. The escalation loop is entered only after a *validation* failure. |

### Task 4b — stop `gather` swallowing a rate limit as an alignment failure

| # | Requirement | Where met | Note |
|---|---|---|---|
| 4b.1 | `from herder.limits import RateLimited` in gather | `packages/llama/src/llama/stages/gather.py:8` | llama-side import from herder — the correct direction. |
| 4b.2 | **`except RateLimited: raise` placed ABOVE the broad clause, not by narrowing it** | `gather.py:993-999`, with `except (TaskFailed, HerderError) as err:` untouched at `gather.py:1000` | **Confirmed done the required way.** The broad clause is byte-identical to before; the new clause precedes it and carries the brief's comment verbatim. This is the spec's explicit legibility requirement (Integration, swallow-site note). |
| 4b.3 | Test asserts `RateLimited` **propagates** | `packages/llama/tests/test_stage_gather.py:281-284` | `with pytest.raises(RateLimited): run_gather(...)`. |
| 4b.4 | Test asserts **no wrong flag persisted** | `test_stage_gather.py:286` | `assert not sws.show.exists()`. See Finding M4 for why this is accepted (and stronger) rather than a flag-string assertion. |
| 4b.5 | Test genuinely reaches the `align_structure` fallback branch | `test_stage_gather.py:285` | **Verified three ways** — see "Branch-reachability adjudication" below. |
| 4b.6 | Test file home | `packages/llama/tests/test_stage_gather.py` | **Adjudicated: correct.** See below. |
| 4b.7 | Mutation evidence (spec Testing, mutated-not-merely-run item 3) | Report §4b, "Mutation evidence" | Clause removed → RED (`DID NOT RAISE RateLimited`, plus the swallow-and-warn `WARNING ... gather.py:994 align_structure failed`), restored → GREEN 92. `__pycache__` cleared on both sides. Accepted. |

### Global constraints

| # | Requirement | Status | Note |
|---|---|---|---|
| G1 | `herder` must not import `llama`/`emcee` | ✅ | `grep` over `packages/herder/src` finds no `llama`/`emcee` import. Task 4b's dependency runs llama→herder only. |
| G2 | Python 3.11+, no new third-party deps | ✅ | Nothing added; stdlib + existing `herder` modules only. |
| G3 | Tests offline, deterministic, no real `$HOME`, no real sleeping | ✅ | `tmp_path` throughout; `tasks._sleep` monkeypatched in both Task 4 tests; `subprocess.run` patched in Task 3 tests. `capture_failure` reads the wall clock only to name the file (`failures.py:38`) — nothing asserted depends on it. |
| G4 | Commit style `type(scope): subject` + test command in the body | ✅ | All three; each body carries both the file-scoped and the full-suite command with counts. `682240d` additionally records the mutation run and the brief/filename deviation. |
| G5 | Suite green at each commit (1678 / 1680 / 1681, 7 deselected, +7 over a 1674 baseline) | ⚠️ | Not re-run, per instructions. Arithmetic is self-consistent: 4 + 2 + 1 = 7 new tests, and the counts step 1674→1678→1680→1681 exactly. |

---

## The invariant, end to end (traced independently)

A `claude -p` refusal naming a session limit, followed from the subprocess to the CLI:

1. **`claude_cli._run` — five failure paths, audited individually.**
   - `subprocess.TimeoutExpired` / `FileNotFoundError` (`claude_cli.py:125-126`) — no `proc` exists; a limit message cannot arrive here. Not classifiable by construction. ✅
   - **`returncode != 0` (`claude_cli.py:128-133`) — the measured path** (the captured signature is exit 1). `_error_detail` (`claude_cli.py:87-108`) pulls the envelope's `result`, else stderr, else stdout, so the refusal text reaches `message` from any of the three sources. `classify` → `RateLimited`. ✅
   - **`is_error` envelope (`claude_cli.py:140-145`)** — classified. ✅
   - JSON-decode failure (`claude_cli.py:136-138`) — captured, **not** classified (Finding M1).
   - Non-string `result` (`claude_cli.py:147-148`) — neither captured nor classified (Finding M1).
2. **`herder.limits.classify` (`limits.py:99-105`)** matches `hit your session limit` (case-insensitive, `limits.py:33`) → `RateLimited(scope="five_hour", resets_at=parse_reset(...))`. `RateLimited` subclasses `HerderError` (`limits.py:53`), which is what makes every downstream ordering load-bearing.
3. **`tasks._with_transport_retry` (`tasks.py:37-47`)** — `except (TaskFailed, ResearchNotSupported, RateLimited): raise` fires **before** `except HerderError`. One provider call, zero backoff. ✅ **Un-retried.**
4. **`run_json_task` / `run_research_task`** — neither catches `HerderError`; the ladder-escalation loop is only re-entered on a *validation* error. So no tier escalation and no second provider is tried. ✅
5. **`llama.stages.gather.run_gather`** — the `align_structure` fallback at `gather.py:986-1001` now re-raises at `993-999`, ahead of the broad clause at `1000`. `write_artifact(show_ws.show, show)` is at `gather.py:1138`, ~145 lines later, so the abort happens strictly before `show.json` is written: **no `low-confidence structure alignment` flag can be persisted.** ✅
   - gather's other LLM call site, `extract_setlist` (`gather.py:795`), is **unwrapped** — nothing to swallow it. ✅
6. **`llama.pipeline.process_show` (`pipeline.py:45-95`)** — audited: **no `except` of any kind** in the file. Every stage propagates. ✅
7. **`cli.py:237`** — `except (TaskFailed, HerderError, IAError)` in `_execute._process`. **Still swallows**: it prints `FAILED <id>`, appends to `failures[]`, and moves to the next show. **This is the later task and is expected to be unfixed — not faulted here.** Its fix is spec'd at Integration §3 (catch `RateLimited` *before* this clause; do not append to `failures[]`).

**Remaining `except HerderError` sites on/near this path** (full audit of `packages/llama/src`, `packages/herder/src`, `packages/emcee/src`):

| Site | On the `_execute` path? | Assessment |
|---|---|---|
| `packages/llama/src/llama/cli.py:237` | **Yes** | The one remaining swallow. Later task, by design. |
| `packages/llama/src/llama/cli.py:2505` (`main_cli`) | Outermost boundary | Not a state-damaging swallow — it prints `error: <msg>` and exits 1. Phase 2's `_execute` catch sits inside it. **But the spec's audit note misidentifies this line** — see Finding M2. |
| `packages/llama/src/llama/cli.py:1902` | No (batch `redo` loop) | Would turn a limit hit into `FAILED <slug>` per show and keep going. Outside `_execute`, so outside phase 1's guarantee. See Finding M3. |
| `setlistfm.py:96`, `jerrybase.py:128`, `correspondence.py:307`, `audio.py:37` | No | Confirmed non-LLM call sites; the spec's audit is correct on all four. |
| `emcee/cli.py:632` | No (separate binary) | Out of scope for this spec. |

**Conclusion: the invariant holds** from the backend to `_execute`'s door on the `claude_cli` backend, with `cli.py:237` the single, expected, already-planned gap.

---

## Branch-reachability adjudication (Task 4b)

The brief warns that a test which never enters the `align_structure` fallback would
pass for the wrong reason. The branch needs: no usable jerrybase evidence,
non-empty `canonical.items`, `result.coverage < align_coverage_threshold`, and
`align_provider is not None` (`gather.py:982-986`). Verified three ways:

1. **Setup provenance.** The test reuses `test_gather_llm_alignment_garbage_falls_back_and_flags`'s
   exact fixture manipulation — retagging every `VBR MP3` file to `Track N` so
   deterministic alignment cannot match and coverage falls under threshold — and
   that neighbouring test is *known* to land in the broad clause today.
2. **In-test assertion.** `assert align_fake.calls, "align_structure LLM was not invoked"`
   (`test_stage_gather.py:285`). `align_fake` is passed only as `align_provider`, and
   `align_provider` is referenced in exactly two places in `gather.py` (the signature
   at `:821` and the fallback at `:986-988`), so a non-empty `calls` list can only mean
   the fallback ran. `FakeProvider.complete` appends to `calls` *before* `_serve` raises
   (`fake.py:20-24`), so the record survives the exception.
3. **Red-run evidence.** The pre-fix run's captured log shows
   `WARNING llama:gather.py:993 align_structure failed: You've hit your session limit` —
   which is the broad clause inside that branch firing. Nothing else in the tree emits it.

Additionally, the test is a genuine *cross-task* check: `FakeProvider` is queued with a
single item, so had Task 4's no-retry fix been absent, the retry would have hit
`AssertionError("no queued complete responses left")` rather than `RateLimited`. The
4b test therefore also pins Task 4's behaviour at the llama call site.

**Test-file home: correct.** `packages/llama/tests/test_gather.py` does not exist
(`ls packages/llama/tests | grep gather` → `test_stage_gather.py` only), and
`test_stage_gather.py` is the sole file importing `run_gather`. The brief's stated
intent — "reuse whatever fixture that file already uses to drive `run_gather`" — is
satisfied only by that file. **Brief naming error, not an implementation deviation.**
The implementer flagged it in both the report and the commit body, which is the right
handling.

---

## Scope creep

**None. Exactly the six intended files**, verified per commit:

- `e4c0786`: `packages/herder/src/herder/claude_cli.py`, `packages/herder/tests/test_claude_cli.py`
- `cb0b5ff`: `packages/herder/src/herder/tasks.py`, `packages/herder/tests/test_llm_tasks.py`
- `682240d`: `packages/llama/src/llama/stages/gather.py`, `packages/llama/tests/test_stage_gather.py`

(`test_stage_gather.py` substitutes for the brief's non-existent `test_gather.py`; it is
the intended sixth file.) Working tree clean; no stray artifacts.

**`set_capture_dir` is NOT called from production code** — verified by grep across
`packages/` and `scripts/`: the only call sites are `test_claude_cli.py:250,255` and
`test_failures.py` (six calls, all `tmp_path` + reset). The sole production consumer of
`failures.py` is `capture_failure`, called three times in `claude_cli.py`. **Capture stays
off by default; switching it on remains the later CLI task.** ✅

No config keys, CLI flags, `pacing.py`, `UsageMeter`, or session-state changes leaked in —
all correctly deferred to their own implementation-order steps.

---

## Exact-value fidelity

| Brief literal | Implementation | Verdict |
|---|---|---|
| Task 3 `_run` replacement block | `claude_cli.py:128-145` | **Identical**, statement for statement. |
| Task 3's four tests | `test_claude_cli.py:222-257` | **Verbatim**, plus a `# --- rate-limit classification and failure capture ---` section header. **Benign.** |
| Task 3 import placement ("add to the imports at the top") | `claude_cli.py:9-10` | Matches. |
| Task 4 `except (TaskFailed, ResearchNotSupported, RateLimited):` | `tasks.py:40` | **Identical.** Brief said "line 36"; it is now line 40 because the docstring grew — positional drift only. **Benign.** |
| Task 4 docstring paragraph | `tasks.py:31-34` | **Verbatim.** |
| Task 4's two tests + `CountingLimitProvider` | `test_llm_tasks.py:191-221` | **Verbatim**, plus a section header. **Benign.** |
| Task 4b `except RateLimited: raise` + comment | `gather.py:993-999` | **Verbatim**, including the five comment lines. Placement above the broad clause as required. |
| Task 4b test | `test_stage_gather.py:272-286` | Follows the brief's shape (`pytest.raises` + no-flag assertion) with the file's real helpers (`FIXTURE`, `StubIA`, `make_candidate`, `IDENT`, `ShowWorkspace`); the brief only sketched `run_gather(...)`. **Benign — the brief delegated this explicitly.** |
| Both `RateLimited` imports as `from herder.limits import ...` | `tasks.py:7`, `gather.py:8` | Matches the briefs. `herder/__init__.py` also re-exports it, so `from herder import RateLimited` would work in `gather.py` — a style inconsistency only (Finding M6), and the deep import is *required* in `tasks.py` to avoid the cycle. |

No divergence rises above benign.

---

## Findings

**M1 (Minor) — two `_run` failure paths remain unclassified, and one is uncaptured.**
`claude_cli.py:136-138` (JSON-decode failure) captures but does not `classify`; the
non-string-`result` path at `:147-148` does neither. The spec says `RateLimited` is
"raised from `claude_cli._run`'s existing failure paths" without enumerating them, and
Task 3's brief specified exactly the two branches implemented — the measured signature
arrives with exit 1, so both implemented branches cover the observed reality. A refusal
delivered as non-JSON stdout with exit 0 would still degrade to a plain `HerderError`
and be retried three times. Not a defect against the brief; worth a line in a later
task, together with a capture on the non-string-`result` branch (a `proc` exists there,
so capture is possible and would cost one line). Note also that `e4c0786`'s commit body
claims "Every failure branch also calls `capture_failure()`", which is not quite true.

**M2 (Minor) — the spec's own swallow-site audit misidentifies `cli.py:2505`.**
The Integration note says `cli.py:1902`/`cli.py:2505` "belong to `fix`/`triage`, outside
`_execute`". `cli.py:1902` is indeed the batch-`redo` loop, but `cli.py:2505` is
`main_cli`, the **global** entry-point boundary — it wraps `_execute` too. It is not a
harmful swallow (it prints `error: <msg>` and exits 1, persisting no wrong state, and
phase 2's `_execute` catch will sit inside it), so **no code change is warranted here**.
Flagged so the spec's audit line can be corrected rather than trusted verbatim by the
`_execute` integration task.

**M3 (Minor) — `cli.py:1902` will still burn a limit hit per show, outside `_execute`.**
`llama redo --held --from ...` over N shows catches `HerderError` per show, prints
`FAILED <slug>`, and continues — so one exhausted window costs N refusals. Correctly out
of scope for phase 1 (the spec scopes the guarantee to `_execute`), but it is a real
residual of the same class and belongs on the backlog beside the `fix`/`triage` sites.

**M4 (Minor, accepted) — the "no wrong flag" assertion is indirect but fails safe.**
The brief asked for "no `low-confidence structure alignment` flag was written"; the test
asserts the stronger `not sws.show.exists()`. That is the better assertion — the defect's
actual harm is a *file on disk* that `should_run` then refuses to recompute, and there is
no `Show` object to inspect on the abort path. It also fails safe: if a future refactor
moved `write_artifact(show_ws.show, show)` ahead of the alignment block, the assertion
would go red rather than silently weaken. Accepted as-is; no change requested.

**M5 (Minor) — the OpenRouter backend does not classify a 429.**
`openrouter.py:37` raises a bare `HerderError(f"openrouter returned {resp.status_code}: ...")`,
so on that backend a rate limit is still retried as transport noise. The spec scopes
classification to `claude_cli._run`, and the measured signature is claude-specific, so
this is **out of scope, not a defect** — but the invariant's reach is backend-specific
and should be stated as such wherever the phase is summarized.

**M6 (Minor, style) — mid-file imports in both new test blocks.**
`from herder.limits import RateLimited` appears at `test_claude_cli.py:219` and
`test_llm_tasks.py:181` rather than in the header block. This is literally what the
briefs' "append this" instruction produces, and no linter is configured in the repo
(no ruff/flake8 config, no lint CI step), so nothing fails. Cosmetic; defer to the
code-quality reviewer.

---

## ⚠️ Cannot verify from the diff

- **Suite counts and greenness at each commit** (1678 / 1680 / 1681, 7 deselected, from a
  1674 baseline). Not re-run per instructions. The arithmetic is internally consistent
  (+4, +2, +1 = the +7 claimed) and each commit body records its own run.
- **The red-state runs** (Steps 2 of each brief) and the **4b mutation run**. Reported with
  specific, plausible failure text — `assert 3 == 1` for Task 4, `DID NOT RAISE RateLimited`
  plus a `gather.py:993/994` warning line for 4b, `assert 0 == 1` for the capture test.
  The line-number shift between the two 4b log quotes (993 pre-fix vs 994 mutated) is
  consistent with the clause being added and removed. Accepted on the report's evidence.
- **Mutation evidence for spec Testing item 2** (`RateLimited` in the no-retry set) was not
  run as a separate mutation. It is not required yet — the spec places the mutation pass at
  implementation-order step 7 — and Task 4's TDD red run *is* the mutant (the pre-fix tuple
  is exactly the flipped constraint, and it produced `assert 3 == 1`). Noted so step 7 can
  record it rather than rediscover it.
- **Whether the false-positive cross-check** ("herder changes" → *False-positive guard*:
  demote a `RateLimited` back to a transport error when a fresh snapshot reads far below
  threshold) will fit `claude_cli._run` as written. It is correctly deferred — it depends on
  `read_usage_snapshot`, which is implementation-order step 3 — but whoever lands the
  snapshot reader must revisit `claude_cli.py:128-145`, since that is where the demotion
  has to happen. No hook exists there today.

---

*Reviewed independently. `progress.md` and all `*-verdict.md` files were not read.*
