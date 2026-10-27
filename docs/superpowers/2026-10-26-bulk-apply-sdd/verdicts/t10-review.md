# Task 10 review (t10-review): `reapply --with-gather-llm`, range a2e0f20b..120b0405

### Spec Compliance

- ❌ One narrow deviation (severity Minor). Everything else matches the brief.
  - `reapply.py:230` (diff line 288): `called = bool({"align_structure", "stored alignment llm"} & set(legs.needs_llm))` decides whether align was called from the FIRST (provider-less) pass. The brief says `align_reproduced` is set "when the stored alignment was `llm` or `align_structure` was called". Gather reaches align only when `today_llm = bool(canonical.items) and ...` (`gather.py:1884`). A show whose only verdict is `extract_setlist` has an empty canonical in the first pass, so align is never reached and `align_structure` is never recorded. In the recompute, the fresh extraction supplies items and `align_structure` can then be called, but `align_reproduced` stays None. This affects only extract_setlist-only shows whose stored alignment is not `llm`. Those rows drop out of the trial's reproduction rate (Task 15 `trial-report`). Fix: count actual calls. Wrap `providers["align_structure"]` in a counter (`pipeline._CountedProvider` already exists), or have `GatherResult` report that align was called, and set the flag on `stored alignment llm in first needs_llm or align calls > 0`.
- ⚠️ Cannot verify from the diff: that Task 13 persists `align_reproduced` and `kind` into `progress.jsonl` (plan line 469), and that Task 15 reads them. In this task the field lives only on `ReapplyOutcome` (`reapply.py:88`; `cli.py` has no reference to it). That is consistent with the plan, but the controller should confirm it at Task 13.

Requirements checked against the diff:
- `GATHER_LLM` holds exactly the three verdicts (`replay.py`, diff line 382), pinned by `test_gather_llm_set_names_the_three_verdicts`. ✓
- `compute_legs(gather_providers=..., llm_failures_raise=...)`: the providers go to `compute_gather`, and with providers the `stored alignment llm` verdict is not appended (diff lines 442-458). ✓
- `compute_gather(llm_failures_raise=False)`:
  - The `align_structure` `except (TaskFailed, HerderError)` arm re-raises when True (diff lines 520-522). ✓
  - `RateLimited` keeps its own arm above it, unchanged. ✓
  - `extract_setlist`: the claim that it "already raises" is verified. `run_json_task` in `build_canonical` (`gather.py:971`) has no try, and `title_inputs` calls `build(kept)` without one. ✓
  - The default-degrade pin and the raise pin are both present (`test_stage_gather.py`, diff lines 805-823). ✓
- Gate `with_gather_llm and legs.needs_llm and set(needs_llm) <= GATHER_LLM` (`reapply.py:222`). With `no vetting.json` present the set is not a subset, so the show stays `needs-llm` (`test_no_vetting_json_stays_needs_llm`). ✓
- Dry run returns `dry-run: needs-llm` before any call (diff line 281). ✓
- Delivered shows: strict `plan_reuse`/`check_pairs` runs before the recompute for every delivered show (`strict=not allow_download` inside `if delivered`, which equals Task 9's `delivered and not allow_download`). The plan is reused at the package step (`reapply.py:291-293`). ✓
- The recompute runs with `llm_failures_raise=True` before any write. Afterwards the show continues as Task 9, and every committed outcome gets `kind = "needs-llm"` (diff lines 352-353). ✓
- `_align_reproduced` compares filenames, set labels, segues and `set_breaks` (diff lines 177-182). ✓
- `--with-gather-llm` is on both CLI forms (diff lines 32-35, 59-60, 80, 103-104, 127-128). ✓

### Cross-task invariants (each checked)
- Task 2's `split_overruled` at the end of `compute_gather` is intact (`gather.py:2248`). The `overrules` pass-through in `compute_legs` (vet `overrules=read_overrides(ws).overrules`, `replay.py:645`) is unchanged context. ✓
- reapply's fresh brief still passes `overrules=overrides.overrules` (`reapply.py:315`) and splits what comes back with `split_overruled(problems, overrides.overrules, final_show)` (`reapply.py:319`). ✓
- A delivered show is checked before any align call. Proven by a mutant: removing the `if delivered:` pre-check makes `test_unpaired_delivered_show_spends_no_align_call` fail at `assert align.calls == [] ...`, as predicted.
- An LLM failure escapes before any write and is counted toward the stop. Proven by a mutant: setting `llm_failures_raise=False` in the recompute makes `test_with_gather_llm_align_failure_is_a_retryable_row_failure` fail at `FAILED` count 0 != 3, as predicted. `STOP_AFTER_LLM_FAILURES` is unchanged (still 3; the diff does not touch it).
- `RateLimited` passes through: gather's arm is unchanged, the list runner's `except RateLimited` still sits above `except (TaskFailed, HerderError)` (diff lines 129-135), and `test_refusal_on_the_align_call_writes_nothing` covers it. ✓
- Untouched-names grep over the diff's +/- lines found no hits for `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES` (one test assertion only), `load_list`, `briefing_reusable`, `purge_package_audio`, any junk or piece-3 constant, `MIN_ANCHORS`, or the pairing rule. The only hits are `check_pairs` call-site moves. ✓
- Named risk: `_station_dir` was moved earlier, ahead of the held/needs-llm returns. I checked `reapply.py:91-92`: it is pure (`config.delivery_path / name` or None) and never raises, so the move changes no behaviour. ✓
- Named risk: production `make_providers` might lack the `extract_setlist`/`align_structure` keys (the tests use hand-built dicts). I checked `pipeline.py:25-32`: `TASK_KEYS` contains both. ✓

### Checks run
- `./.venv/bin/python -m pytest <the 3 touched test files> -q -k <task 10 tests>`: 33 passed.
- Mutation run in a scratch copy (`git archive HEAD | tar -x`; worktree venv's python with `-m pytest -p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` shadow; `llama.__file__` and `herder.__file__` both verified inside each copy; run from the copy's cwd):
  - m0 (baseline): 3 passed.
  - m1 (pre-check removed): the predicted test failed.
  - m2 (`llm_failures_raise=False`): the predicted test failed.
- Log: `t10-review.log`.

### Strengths
- The change is small and well placed. A single switch on `compute_gather` keeps today's degradation for every other caller, and both sides are pinned.
- The pre-check plan is reused at the package step rather than computed twice (`reapply.py:291`).
- `extra` merged into `result()` means `align_reproduced` reaches every later outcome, including `skipped: structure changed`.
- The tests exercise real gather/align paths through the fixture library with `FakeProvider`, not mocks of `compute_legs`. Two load-bearing guards were shown, by mutation, to be pinned.

### Issues

#### Critical
None.

#### Important
None.

#### Minor
1. `reapply.py:230`: `align_reproduced` is inferred from the first pass's verdicts, not from actual calls. See Spec Compliance above (the one spec deviation).
2. `reapply.py:212-217` and `231-239`: the `mkdtemp` / `compute_legs(... CacheOnlyIA, setlistfm_client ...)` / `rmtree` block appears twice, differing only by two kwargs. A small `_legs(**kw)` helper would remove it.
3. Test coverage:
   - No test drives the `extract_setlist` leg of the recompute. There is no fake `extract_setlist` response, and no extract failure under `llm_failures_raise`.
   - The brief's row-failure test asks for a provider that raises `HerderError`. `test_reapply.py:704` uses garbage JSON (`TaskFailed`) instead. The same except arm catches both, but the transport `HerderError` path is not exercised at reapply level, and `test_compute_gather_llm_failures_raise` likewise uses `TaskFailed` only.
4. `test_reapply.py:700-701`: `for e in held: e.ws.vetting.exists()` is a no-op statement (dead code).
5. `test_reapply.py:575`: `_needs_align(root, config)` never uses `config`.
6. `_align_reproduced` (`reapply.py:114`): no test pins the `set_breaks` leg, so a mutant dropping it would likely survive. This is coverage polish.

### Assessment

**Task quality:** Approved. The Minors are optional. The spec deviation (Minor 1) is the one worth fixing before the trial.

**Reasoning:** The gather-LLM path is correctly gated and ordered: the station check comes before spend, and failures escape before any write and are counted. All of this was verified by reading and by two predicted mutants. The only defect is that `align_reproduced` can be left unset for extract_setlist-only shows whose recompute does call `align_structure`.
