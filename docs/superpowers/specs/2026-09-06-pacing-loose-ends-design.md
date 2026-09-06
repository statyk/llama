# Usage-pacing loose ends — design

Date: 2026-09-06
Status: approved (brainstormed 2026-09-06)
Base: `origin/main` @ `2386eb9`, suite 1871 passed / 7 deselected

Closes the follow-ups left by the usage-pacing phases. Phase 1 (reactive
pause), phase 2 (proactive gate) and T7b (`--wait` at the run-level sites) all
shipped; the ledger
`docs/superpowers/2026-09-05-usage-pacing-phase2-sdd-ledger.md` handed four
named items to a later phase. This is that phase.

## Scope

Four items, in the order they are worth doing:

1. **T6b** — a `RateLimited` during `run_interpret` still exits 1 with no
   checkpoint. Prevent it, then survive it.
2. **Render the `per_model` meter** in `llama pacing` and the run-start line.
   Render only; `decide()` is untouched.
3. **The "resume costs nothing" test** — a call-counting provider proving
   already-packaged shows make zero LLM calls on re-entry.
4. **Generalize the config-template key-set assertion** so a key missing from
   `DEFAULT_CONFIG_TOML` reddens the suite.

### Closed as won't-build

**`Progress`'s two counters** (shows-done, shows-remaining), which the phase 2
spec originally named. No policy rule consumes them and `_execute` sizes its
own forecast against `count` at the call site, so building them adds an
unconsumed field. R29 parked them; this spec closes them. The phase 2 spec's
"filed and unbuilt" marker should be updated to say *closed*, not *pending*.

### Out of scope, named so it is not a surprise

- **`profile_add`'s `run_interpret` call.** It runs against a scratch
  workspace with no session to park, so there is nothing to checkpoint. A
  limit there still exits 1.
- **openrouter pacing.** Still an explicit non-goal;
  `herder/openrouter.py` raises a plain `HerderError` on any non-200 and
  stays untouched.
- **Binding `per_model` in `decide()`.** See item 2 for the evidence bar.

## 1. T6b — prevent, then survive

### The problem, restated

The filed cost of T6b was "one wasted LLM call". That understates it. The
pre-flight pacing gate lives at the **top of `_execute`**, and in query mode
`_get_query` calls `run_interpret` *before* `_execute`. So on
`llama get "..."` the interpret call is the first LLM call of the run and it
is spent with **no proactive check at all**. Start an unattended run with
`--wait` (the default) when the 5-hour window is nearly gone and it does not
pause and nap — it raises, exits 1, and does nothing all night. The unattended
run that pacing exists for is defeated by its own first call.

`run resume` cannot cover this today because `run_interpret` writes
`criteria.json` only on success and `run resume` refuses a session without
one. The query lives only in argv. That is why T6b is a resumability design
and not a `try/except`.

### (a) Prevent — gate before interpret

Extract `_execute`'s pre-flight gate loop (the `while True:` around `_meter` /
`decide` / `_render_pause`) into a helper, and call it from `_get_query`
before `run_interpret` as well as from `_execute` where it lives today.

`_execute` keeps its own gate. It has four other entry points
(`_get_profile`, `run_approve`, `run_resume`, `_redo_run_level`) and must not
depend on a caller having gated first.

**Accepted cost, stated rather than engineered away:** a query-mode run start
now performs two meter reads instead of one. Each is a `claude -p "/usage"`
subprocess — zero tokens, ~0.5–3 s. Threading one reading through five call
sites to save it would add shared state to the exact path this spec is trying
to make simpler.

### (b) Persist — `request.json`

`_get_query` writes a new run artifact immediately after `claim_run_dir`,
before any LLM call:

```
runs/<id>/request.json
  { "query": <raw argv string>,
    "limit": int|null, "artist_cap": float|null,
    "min_score": float|null, "year_cap": float|null,
    "auto": bool, "plan": bool }
```

`RunWorkspace` gains a `request` path beside `criteria`. The flags are the
same ones `_get_query` stamps into criteria after interpret, captured here so
a resume replays them identically rather than reconstructing them from
defaults.

This is the artifact whose absence made T6b impossible as a catch.

### (c) Survive — catch, park, resume

`run_interpret` in `_get_query` is wrapped in `except RateLimited`, routed
through the **existing `_render_pause`** — the one renderer already shared by
the pre-flight gate, the run-level catch and the show loop. That gives the new
site the timing arithmetic, the sleep-or-checkpoint decision and the
KeyboardInterrupt contract for free, and it means the site honours
`--wait`/`--max-wait` exactly as the other three do.

Two properties carry over and must hold here:

- **At most one nap.** Nothing completes between naps at a site where no work
  has run, so the second pause passes `stalled=True`. Without it a `when`
  already in the past makes `sleep_until` return immediately and the pause
  becomes a hot spin — a hang, not a red test.
- **Exit 0, not 1.** A checkpoint is a parked run, not a failure.

The checkpoint is `sessions.mark_paused(..., scope="interpret")`.

`run resume` gains one branch, and only one:

- no `criteria.json` **and** `request.json` present → re-run interpret from
  the persisted query, re-apply the stamped flags, continue into `_execute`;
- no `criteria.json` **and** no `request.json` → today's refusal message,
  unchanged (this is the pre-existing "not a llama run dir" case).

### (d) `run list` shows the query

`sessions.iter_sessions` defaults `SessionInfo.query` to `""` when there is no
`criteria.json`, so a run paused at interpret renders on `llama run list` as
an empty pair of quotes — the one run whose query the operator most needs to
see. `iter_sessions` falls back to `request.json`'s `query` when `criteria.json`
is absent.

### Tests

- A `RateLimited` raised from `run_interpret` under `--no-wait` produces a
  `paused` session with a `resume_after` and exit 0, not a traceback.
- The same under `--wait`, with a reset inside `max_wait`, sleeps once and
  retries interpret.
- `run resume` on such a session re-interprets from `request.json` and
  completes; the stamped flags survive the round trip.
- The pre-flight gate fires *before* interpret: a verdict of `PauseUntil` at
  run start spends **zero** interpret calls (assert on a call counter, not on
  output).
- `run list` renders a paused-at-interpret session with its query, and
  `run list --json` does not crash on the missing `criteria.json`.
- `run resume` on a dir with neither artifact still refuses with today's
  message.

## 2. Render `per_model`

`herder.usage` already parses `per_model` into `UsageReading`; nothing renders
it. `_pacing_line` gains one more conditional part, in that function's
existing style:

```
pacing: 5h 12% · weekly 40% · Fable 42% · est 3.1%/show · ~17 fit before 5:19pm
```

Keyed by the account's own label (`Fable` here, model-dependent elsewhere),
entries sorted by key, and the part omitted entirely when the dict is empty —
following the rule already in `_pacing_line`'s docstring that rendering a
placeholder for a genuinely-unknown value reads as a measurement.

**`decide()` is not touched**, and a test pins that: a reading carrying a
per-model meter at 99% must still verdict `Proceed`.

**The evidence bar for binding it later**, recorded so the decision is not
re-litigated from taste: a refusal captured under `~/.llama/llm-failures` that
actually names the per-model window. Until then, binding on an
account-dependent key risks pausing an unattended run for hours against a
window llama never spends — strictly worse than the reactive catch that
already handles a real refusal.

## 3. "Resume costs nothing"

A counting wrapper over the `fake` provider. Package a show, then `run resume`
the same run dir, and assert the already-packaged show drives zero LLM calls
on re-entry (the property is `should_run`'s; the test is what stops a later
change from quietly losing it — `CLAUDE.md` advertises it to operators).

**The test asserts the counter is non-zero on the first run before asserting
zero on the resume.** This branch hit the empty-result failure mode five
times, twice as a scoring harness that graded a crashing control as clean. A
bare "zero calls" assertion passes just as happily when the run never
happened.

## 4. Config-template key-set assertion

`test_default_config_template_matches_defaults` compares parsed *behaviour*,
so a key omitted from `DEFAULT_CONFIG_TOML` yields its model default and the
comparison still passes. It catches a wrong value, never an absent one. Phase
2 added a key-set assertion scoped to `[pacing]`; this generalizes it.

**Measured 2026-09-06: the template is complete today.** `root`,
`delivery_path`, `setlistfm.api_key` and the tier tables are all present as
commented-out examples. So this lands green and changes no template text — it
is bit-rot protection, and its design follows from that measurement: the
assertion **must read commented lines**, or it would fail on a correct
template.

Per section: keys = parsed TOML keys ∪ keys matched by `^\s*#\s*(\w+)\s*=`
within that section's span, compared against the section model's
`model_fields`. Top-level scalars checked the same way against `Config`.

Exempt, with the reason named in the test: `llm` and `tiers` are free-form
maps (`dict[str, LLMTaskConfig]`, `dict[str, dict[Tier, str]]`) with no fixed
key set to assert against.

**Mutation check, with the prediction named first** (per the project's
"mutation scoring needs a prediction" rule): deleting `five_hour_ceiling` from
`DEFAULT_CONFIG_TOML` must redden *this* test by name — not merely produce
some failure somewhere.

## Constraints to mutate, not merely run

1. Delete a documented key from `DEFAULT_CONFIG_TOML` → item 4's test, by
   name, goes red.
2. Drop the `stalled=True` argument at the new interpret pause site → the
   second pause becomes a hot spin. **This one hangs rather than reddening**;
   it is verified by reading the call site and by a bounded-timeout run, not
   by a sleep-budget assertion, which structurally cannot see it.
3. Remove the `request.json` write → the resume test fails with today's
   refusal message.
4. Make `decide()` read `per_model` → item 2's `Proceed` test goes red.

## Risks

- **Two meter reads at query-mode run start.** Accepted above; measurable as
  ~0.5–3 s of wall clock, zero tokens.
- **`request.json` is a new run artifact.** `run rm`, `_resolve_run` and
  `attention_sessions` key off the run dir and `session.json`, so none of them
  need to know about it; item 1(d) is the one place that reads it.
- **A resumed interpret is a fresh LLM call.** Re-interpreting the same query
  can in principle yield different criteria than the interrupted call would
  have. This is correct behaviour for a run that never persisted criteria, and
  is the same exposure `redo --from interpret` already carries.
