# Final whole-branch review — `pacing-loose-ends`

Reviewer: Opus, whole-branch gate. Worktree `/Users/shawn/projects/llama-wt-pacing-loose-ends`,
branch `pacing-loose-ends`. Worktree left byte-for-byte untouched (`git status --short`
empty at start and end; every mutation ran in an `rsync`ed copy with `__pycache__`
excluded and shadowing proven under pytest).

**Note on the range:** the brief names `c1bac37`; the branch HEAD is **`34e3f69`**, one
commit further. `git diff --stat c1bac37..34e3f69` is 21 files, **all under
`docs/superpowers/2026-09-06-pacing-loose-ends-verdicts/` and `.../implementer-reports/`
— zero code**. So the code diff is exactly `660f588..c1bac37` as briefed, and everything
below was verified at HEAD. The ledger's Progress section stops at Task 7 / `c1bac37`
and does not mention `34e3f69`; that is bookkeeping only.

---

## Overall verdict

**APPROVE — merge as is.**

Seven tasks touched `cli.py` and four touched `_get_query`, and the result reads as one
design, not seven edits. `_get_query`'s control flow — validate caps → `claim_run_dir` →
persist `request.json` → resolve `pace` → `_preflight_gate` → `_interpret_with_pause` →
`_execute` — is coherent, correctly ordered, and each ordering constraint is pinned by a
mutation I applied myself. The four pause sites genuinely share one renderer. The T6b
story works end to end, including the resume's own gate and catch, and I verified the
round trip rather than reading it.

I found **no Critical findings** and **one Important** one (`--plan` is silently dropped
on the resume the CLI itself recommends). It is not merge-blocking — it is consistent
with pre-existing `run resume` semantics — but it is a ~2-line fix using data the branch
already persists, so I would take it now.

Both measured traps in the ledger are **correctly captured**; I reproduced both
independently. Both were real and both would have misled a re-runner.

---

## Verification evidence (exact commands)

**Interpreter resolves inside the worktree:**
```
cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -c "import llama; print(llama.__file__)"
→ /Users/shawn/projects/llama-wt-pacing-loose-ends/packages/llama/src/llama/__init__.py
```

**Suite (never a bare `pytest`, never a `.venv/bin/*` console script):**
```
cd /Users/shawn/projects/llama-wt-pacing-loose-ends && ./.venv/bin/python -m pytest -q
→ 1891 passed, 7 deselected, 26 warnings in 6.13s
```
Matches the expected 1891 exactly.

**No test lost — `--collect-only` node-ID diff against `660f588`.** Base extracted with
`git archive 660f588 | tar -x` into a scratch dir and collected via `PYTHONPATH` shadow
(shadowing proven: `llama.__file__` resolved inside the extract):
```
base: 1871 node IDs      branch: 1891 node IDs
LOST (base − branch):  1  — packages/llama/tests/test_config.py::test_default_config_template_documents_every_pacing_knob
ADDED (branch − base): 21
```
The single loss is the deliberately retired `[pacing]`-scoped template test, replaced by
`test_the_template_documents_every_config_key`; I verified below that the replacement
strictly dominates it (it restores the equality direction AND extends it to the top
level). 1871 − 1 + 21 = 1891. ✔

**Mutation copy proven, not assumed:**
```
rsync -a --exclude '.venv' --exclude '.git' --exclude '__pycache__' <worktree>/ $S/
# planted test asserting llama.__file__ / llama.cli.__file__ / herder.__file__ all start with $S
cd $S && PYTHONPATH=$S/packages/{llama,herder,emcee}/src <worktree>/.venv/bin/python -m pytest -q packages/llama/tests/test_zz_sentinel.py
→ 1 passed          # pytest really imports the copy
```
Copy baseline `1891 passed, 7 deselected`. After restoring every mutant, `diff -r` copy
vs worktree was empty and the copy was back at `1891 passed`.

### Mutants I applied (prediction named BEFORE each)

| # | Mutant | Predicted red | Observed |
|---|---|---|---|
| M1 | Relocate `_get_query`'s `_preflight_gate` call to *after* `_interpret_with_pause` (gate present, wrong place) | `test_the_preflight_gate_runs_before_interpret_is_paid_for` | **1 failed / 1890 passed**, exactly that test. ✔ ordering pinned, not mere presence |
| M2 | Delete `iter_sessions`' `elif ws.request.exists()` fallback | `test_run_list_shows_the_query_of_a_run_with_no_criteria` + `test_a_limit_during_interpret_parks_a_resumable_session` | 3 failed — both predicted, plus `test_run_list_json_survives_a_session_with_no_criteria`. `test_status_by_run_...` stayed **green**, proving `_by_run_rollup`'s duplicate lookup is *independently* pinned ✔ |
| M3 | `_interpret_with_pause`: `stalled=stalled` → `stalled=False` (run under `timeout 120`) | `test_a_limit_during_interpret_sleeps_at_most_once`, as a **RED test, not a hang** | **1 failed / 1890 passed in 6.5 s.** ✔ — confirms ledger trap 2 |
| M4-A | `_preflight_gate`: `stalled=slept` → `stalled=False`, `-k preflight`, `timeout 60` | **hang, exit 124** | `exit=124` ✔ |
| M4-B | same mutant, `-k test_preflight_re_reads_the_meter_after_the_nap` (the plan's named test) | **PASSES — the trap** | `1 passed, 71 deselected`, exit 0 ✔ |
| M4-C | same mutant, `-k test_preflight_sleeps_at_most_once` | exit 124 | `exit=124` ✔ |
| M5a | `_get_query`'s **inline** interpret dict: `"artist_cap": artist_cap` → `None` | GREEN (unpinned) | `1891 passed` ✔ predicted |
| M5b | `_get_query`'s **persisted** request dict: same substitution | GREEN (unpinned) | `1891 passed` ✔ predicted |
| M5-base | *control:* delete the `artist_cap` stamp from `_get_query` **at `660f588`** | GREEN (pre-existing gap, not a branch regression) | `1871 passed` ✔ |
| M6 | `workspace.should_run` → `return True` | `test_resuming_a_packaged_run_costs_no_llm_calls` | 2 failed, incl. the predicted one ✔ — Ruling T3-1 is effective |
| M7 | Add phantom `reserve = 10` under `[pacing]` in `DEFAULT_CONFIG_TOML` | `test_the_template_documents_every_config_key` | that test alone; `test_default_config_template_matches_defaults` green ✔ |
| M8 | Delete `five_hour_ceiling` from `DEFAULT_CONFIG_TOML` | same test, with `missing={'pacing': ['five_hour_ceiling']}` | exact message observed ✔ |

### Two behavioural probes (temporary test file in the copy, removed after)

- **`--plan` + limit at interpret + `run resume`** → the resumed run **downloaded audio and
  packaged the show**. `"nothing processed"` absent from the output. Measured, see the
  Important finding.
- **KeyboardInterrupt raised from `pacing._sleep` during an interpret nap** → exit 0,
  `STATE_PAUSED`, `resume_after` set, `request.json` intact. The inherited
  `_render_pause` contract holds at the new site. (Ledger filed this as an unpinned
  minor; it is unpinned but it *works*.)

---

## Cross-task coherence

**It reads as one design.** Concretely:

- `_get_query`'s ordering is right and each step's placement is load-bearing and pinned:
  the request write precedes interpret (pinned by
  `test_request_is_written_even_when_interpret_fails`), the gate precedes interpret
  (pinned by M1), the catch wraps interpret only.
- `_interpret_and_stamp` and `_interpret_with_pause` are each a single copy shared by
  `_get_query` and `run_resume`. That is the right factoring: the alternative is two
  stamping rules that drift, which is exactly the failure the spec names.
- All four pause sites route through `_render_pause`, and `--no-pacing` is now handled
  identically at the two sites that re-raise. `CLAUDE.md`'s new paragraph explaining that
  `--no-pacing` *means* different things per site (re-raise / per-show failure / gate goes
  blind) is accurate — I checked all four sites against it.
- `_pacing_line` has exactly two callers (`cli.py:410`, `cli.py:1662`), so spec item 2's
  "both `llama pacing` and the run-start line" holds through one function. No second
  render site exists.
- `decide()` is genuinely untouched and the render-only boundary is test-enforced
  (`test_decide_ignores_the_per_model_meter`).

**The T6b story end to end — it works.** I walked it and it is also asserted:
`test_a_limit_during_interpret_parks_a_resumable_session` does the full round trip
(park → swap the provider → `run resume` → `STATE_COMPLETE` + `criteria.json` now exists
with the original query). The resume's own gate and catch are each independently pinned
(`test_resuming_a_criteria_less_session_gates_before_re_interpreting` on `calls == 0`,
`test_a_limit_while_resume_re_interprets_parks_the_session_again` on the **re-written**
`resume_after`). The brief's premise that "no single task's tests assert it end to end"
is no longer true — Task 7's implementer added the Step-5 chain.

**Things living in unchanged code that per-task reviews could not see, checked:**

- Nothing anywhere deletes `criteria.json` (`_redo_run_level` unlinks only
  `candidates`/`shortlist`; `RUN_LEVEL_STAGES` excludes `interpret`), so the new
  criteria-less resume branch is reachable **only** for a genuinely never-interpreted run.
  No interaction with `redo`.
- `run rm`, `_resolve_run`, `attention_sessions`, `_session_json` all key off the run dir
  and `session.json` and need no knowledge of `request.json`. Spec's risk assessment holds.
- `main_cli`'s error boundary catches `HerderError`, so the `--no-pacing` re-raise prints a
  clean `error: …` and exits 1 rather than a traceback. Same as base behaviour.
- `Config.model_fields` has no `Model | None` field, so the config test's
  "`isinstance(ann, type) and issubclass(ann, BaseModel)`" branch has no silent-skip
  population today. `_FREE_FORM = {"llm", "tiers"}` names exactly the two free-form maps.
- A side effect worth knowing, and a good one: a Ctrl-C *during interpret* (not a limit)
  now leaves a resumable run dir where it previously left one `run resume` refused.

---

## Findings

### Critical
None.

### Important

**I-1. `--plan` is silently dropped on the resume the CLI itself recommends.**
`packages/llama/src/llama/cli.py:1062-1090` (`run_resume`'s criteria-less branch) →
`cli.py:1086` `_execute(...)` with `plan` left at its default `False`;
`request.json` persists `plan` at `cli.py:795` and nothing ever reads it.

Measured, not reasoned: `llama get "…" --plan` refused at interpret parks correctly and
prints `run resume interp`. Following that hint runs the **full acquisition** — my probe
saw six audio files downloaded and the show packaged, with `"nothing processed"` absent.
The operator asked to see a shortlist and got a processed show.

This is *close* to pre-existing (`run resume` on an `awaiting` plan-mode run already
ignores `plan`), which is why I am not calling it Critical. What makes it a finding rather
than inherited behaviour is that in the criteria-less case `llama run resume` is the
**only** recovery the CLI offers and it prints it as the hint, so the surprise is the
tool's doing, not the operator's choice.

Cheapest correct fix, using data the branch already persists — in the criteria-less branch
only, so the criteria-present path is unchanged:

```python
        req = json.loads(ws.request.read_text())
        criteria = _interpret_with_pause(config, ws, req, pace)
        if criteria is None:
            return
        plan = bool(req.get("plan"))     # …and pass plan=plan into _execute below
```
`_execute` then marks the run `awaiting` and prints `llama run approve <run>`, which is
what a plan-mode run is supposed to end at. All four existing resume tests persist
`plan: False` and stay green. I would **not** replay `auto` the same way — `run resume`
has its own explicit `--auto/--interactive` flag and the persisted value must not
override it; either leave `auto` in the artifact as informational (and say so in the
comment) or drop it.

### Minor

**M-1. The `_get_query` request dict is spelled twice and neither spelling is pinned.**
`cli.py:792-795` (persisted) and `cli.py:805-807` (passed to `_interpret_with_pause`).
Measured (M5a/M5b): substituting `artist_cap → None` in **either** one leaves all 1891
tests green. The ledger filed this as a deferred minor on trust; it is now measured.
Mitigating and important: the **base control (M5-base) is also green**, so the `get`-path
cap stamp was already unpinned at `660f588` — this branch does not regress it, it
duplicates an already-unpinned surface. The 3-line fix is to build the dict once and pass
the same object to both, which makes the drift structurally impossible rather than merely
untested. Cheap; not required.

**M-2. `json.loads(ws.request.read_text())` is unguarded at four call sites**, two of them
in read-only sweeps: `sessions.py:127`, `cli.py:2823`, `cli.py:1083`, plus
`test`-side. A malformed `request.json` takes down the entire `llama run list` /
`llama status --by-run` sweep, not one row. Note the asymmetry *inside one function*:
`_read_marker` five lines below (`sessions.py:70-79`) is defensively guarded against
exactly this. Writes are atomic unique-temp + rename and the sibling `criteria.json` read
has identical exposure, so this is not a regression — but any hardening must cover both.

**M-3. `_by_run_rollup` (`cli.py:2816-2823`) duplicates `iter_sessions`' query lookup.**
Deliberately not refactored during the run to avoid widening the `cli.py` conflict
surface, which was the right call at the time. Now that all seven tasks have landed the
refactor is safe, and M2 shows both paths are independently pinned so a broken unification
would redden. Post-merge cleanup.

**M-4. `INTERPRET_NOTE` is unpinned** (`cli.py:714`) — the ledger measured that deleting
`note=INTERPRET_NOTE` leaves 1891 green. Its sibling `PREFLIGHT_NOTE` is pinned only on
its prefix. Operator prose; ship.

**M-5. `_get_query`'s `if pace is None: pace = pace_options(config)` (`cli.py:797`) is
unreachable** — `get` always passes a `pace`. Matches `_execute`'s sibling; defensible as
an invariant. Ship.

**M-6. Ledger bookkeeping:** the Progress section ends at `c1bac37` and does not record
`34e3f69`, the docs-only commit that preserved the 15 verdicts and 6 implementer reports
in-repo. Worth one line at ratification, since that commit is what makes the run's
evidence survive the worktree being removed.

---

## Merge triage of the deferred minors (item by item)

**Must-fix before merge: none.** One I recommend fixing now, and two already fixed.

**Already resolved — verify and strike from the list (I checked both):**
- *Task 4 — stale "the query lives only in argv" comments.* **DONE.** `cli.py:789-791` now
  reads "Persisted BEFORE the first LLM call…"; `sessions.py:98` now reads
  "criteria.query, else request.json's; "" if neither". Task 7's doc step did happen. The
  ledger's Task-5 CHECKLIST ITEM ("the branch must not ship a comment asserting the
  opposite of what its code does") is satisfied.
- *Task 6 — dangling `cli.py:478-480` cross-reference.* **DONE.** That comment now names
  the two in-run call sites and `profile_add` explicitly; nothing dangles.

**Recommend fixing before merge (1 item, ~2 lines + 1 test):**
- *Task 5 — `auto`/`plan` persisted but never consumed.* → finding **I-1**. Fix `plan`;
  leave `auto` to the resume flag. Everything else on this list can wait.

**Ship as is (everything else). Grouped by why:**

*Deliberately out of scope, correctly filed — do not smuggle in:*
- `Config` sets no `model_config`, so pydantic's `extra="ignore"` silently drops a typo'd
  key in a real operator `config.toml`. `extra="forbid"` is a production behaviour change
  that would break anyone carrying a stale key. **Ship; file it in
  `llama-next-steps-and-deferred`** — it is the most valuable item on the whole deferred
  list and it does not belong to this branch.

*Real but bounded, and matching pre-existing exposure:*
- Task 4: unguarded `json.loads` at two read-only sites → **M-2**. Ship.
- Task 5: `request.json` read raw rather than through `read_model` + pydantic. Same
  family as M-2. Ship together, later.
- Task 4: `_by_run_rollup` duplicates the lookup → **M-3**. Ship; refactor post-merge.

*Test-quality observations where the property is covered elsewhere:*
- Task 1: `startswith` in `test_the_line_renders_the_per_model_meter`. The neighbouring
  full-equality tests pin the empty-`per_model` case and the `sorted()` mutant pins order.
  Ship.
- Task 3: the fresh-run mutant reddens the exit-code assertion rather than the final
  equality. I re-measured with M6 — the intended test does redden. Ship.
- Task 5: the `get`-path flag stamp pinned only transitively → measured in **M-1**, and
  measured **pre-existing**. Ship.
- Task 5: monkeypatch inconsistency (tests 2/4 use a fresh-dict lambda); test 4's comment
  overreach; nothing pins that `_get_query` and `run_resume` stamp identically. Ship.
- Task 6: three decorative assertions in
  `test_resuming_a_criteria_less_session_gates_before_re_interpreting`, and re-marking
  unpinned *there*. Note that re-marking **is** pinned at the sibling site
  (`test_a_limit_while_resume_re_interprets_parks_the_session_again` asserts
  `resume_after.startswith("2026-09-07T14:02")`), so the property is not unpinned on the
  branch. Ship.
- Task 7: `stalled` unpinned at the `run_resume` site specifically — same helper, same
  code path, and M3/M4 pin the helper at both of the other two. Ship.
- Task 7: no KeyboardInterrupt assertion at the interpret site — I **probed it and it
  works**. Ship.
- Task 7: `INTERPRET_NOTE` unpinned → **M-4**. Ship.

*Cosmetic / prose / style:*
- Task 1: the bare account label (`· Fable 42% ·`) carries no scope word. It is
  brief-specified and test-pinned; a spec-level revisit, not an implementation slip. Ship.
- Task 2: a wholly commented-out block reads as "documented" — **unavoidable**, the spec
  requires reading commented lines or the test fails on a correct template. Ship.
- Task 2: `_TEMPLATE_KEY` matches prose shaped like `# ident =`; only one nesting level
  checked (`LineageEra`'s own fields unasserted); local `from pydantic import BaseModel`;
  `get(...) + [name]` over `setdefault(...).append(...)`. No current false positive.
  Ship.
- Task 3: 639c6b0's ambiguous docstring parenthetical. Ship.
- Task 4: `write_artifact` already dumps dicts, so the explicit `json.dumps` and the new
  module-level `import json` were avoidable; positional `iter_sessions(tmp_path)[0]`.
  Ship.
- Task 6: brief-authored docstring narrating the pre-fix world in present tense;
  unreachable `pace is None` → **M-5**. Ship.
- Task 7: `config` untyped in the new signature; the `_preflight_gate` cross-reference
  could go stale; `CLAUDE.md`'s four-clause `--no-pacing` sentence. Ship.

---

## My read on your rulings

I re-derived the load-bearing ones rather than reading them. **I think all thirteen were
right.** Notes on the ones that mattered:

- **T2-1 (restore the phantom direction) — right, and stronger than the ruling claims.**
  M7/M8 confirm both directions redden the named test uniquely, and the reverse check now
  works at the top level too, which the retired `[pacing]`-scoped test could never do.
  Calling the plan's one-directional replacement "a narrowing, not a generalization" was
  the correct reading of spec §4.
- **T3-1 (pin re-entry, not cheapness) — right.** M6 reproduces it: `should_run → True`
  reddens the test, and it is the `"packaged:"` line that does the work. Without it the
  test's own name was false.
- **QF-1 (write-before-interpret ordering) — right, and the most important ruling on the
  branch.** It sits at the base of a four-task sequence; a checkpoint written after the
  call it survives is worthless, and the plan's test could not tell the difference.
- **QF-2 (mirror into `_by_run_rollup`, refactor OUT) — right on both halves.** M2 shows
  the two lookups are independently pinned, which is what makes the deferred refactor safe
  *and* verifiable later. Refactoring mid-run across four `cli.py`-touching tasks would
  have been the wrong trade.
- **Gate `run_resume`'s re-interpret (the spec deviation) — right, and I would have
  escalated if it had been left out.** A resume that spends an ungated interpret call
  against the same exhausted window is T6b's defect on the one command that exists to
  undo it. The spec's §1(a) is silent only because the branch created that call site.
  **Fold it into the spec at ratification**, as you noted.
- **Lifting your own test-count gate (Task 5) — right.** The gate exists to catch a test
  being *lost*; the `--collect-only` diff above is the direct check, and it shows 0 lost
  beyond the one deliberate retirement. Counting was never the real instrument.
- **Keep the `--no-pacing` guard — right,** and I verified the premise independently: with
  `HerderError` reaching `main_cli`'s boundary, the re-raise gives a clean `error: …` and
  exit 1, matching base behaviour, and `CLAUDE.md`'s pre-existing "opts out of both halves"
  sentence stays true. Defence of an existing promise, not new scope.
- **Inverting `test_request_is_written_even_when_interpret_fails` — right,** and the
  `--no-wait` catch was a genuine save: that refusal names no reset, so the default
  `--wait` path would have slept a real hour under the 6h cap. That is a CI hang, and it
  was one line from shipping.
- **`PREFLIGHT_NOTE`, `CountingProvider.calls`, three prose Minors pulled into the loop —
  all fine.** The prose ones were the right call under this run's standing rule; a comment
  asserting the opposite of its code is the same defect class as the six test-name
  findings, just aimed at a human instead of a test runner.
- **Spec 1(c)'s `scope="interpret"` — you are right that the code is right.**
  `_render_pause` takes `scope` from `getattr(limited, "scope", None)`, and `pause_scope`
  means the usage window everywhere else. Correct the spec line, leave the code.

**Both measured traps are correctly captured**, and I reproduced each independently:
trap 1 (the plan's Task-6 mutation step names the wrong test) — the named test **passes**
under the mutant, exit 0; the hang is in `test_preflight_sleeps_at_most_once`, exit 124.
Trap 2 (spec constraint 2 is site-specifically false) — at `_interpret_with_pause` the
mutant is a red test in 6.5 s, at `_preflight_gate` it is a hang. Both warnings are
accurate as written and both are worth their space in the ledger; a re-runner narrowing
`-k` to the plan's named test would have retired a live guard.

## The dominant defect class

I looked specifically for a seventh instance of "a test whose name or docstring claims a
constraint it does not pin", since the plan's prescribed test code was the source of six.
I could not find one. Every new test whose name asserts an ordering, a count, or a
re-entry has an assertion that discriminates the wrong implementation from the right one,
and in the three cases I mutated for (M1, M2, M6) the discriminating assertion was the one
added *beyond* the brief. The nearest miss is Task 6's
`test_resuming_a_criteria_less_session_gates_before_re_interpreting`, whose three
decorative assertions are true before the command runs — but its docstring says so
honestly and names `calls == 0` as the load-bearing one, which is exactly right.

The two remaining unpinned claims I found are both **prose about the code**, not test
names: `INTERPRET_NOTE` (M-4) and the twice-spelled request dict (M-1, and pre-existing).
Neither is the class that has been biting this run.
