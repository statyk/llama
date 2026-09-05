### Task 4b: Stop `gather` swallowing a rate limit as an alignment failure

Found in the preflight scan, 2026-09-04, and approved as its own task. `stages/gather.py:992` wraps the `align_structure` LLM fallback in `except (TaskFailed, HerderError)` and merely logs a warning. `RateLimited` subclasses `HerderError`, so a limit hit there is **swallowed**: gather completes, appends a `low-confidence structure alignment` review flag the recording did not earn, and writes it to disk. Stage-level `should_run` then means the resume never recomputes it — so a transient window exhaustion leaves a permanent, wrong review flag on a show. That contradicts the spec's own guarantee that a limit hit means *nothing about the show is wrong*.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (the `except (TaskFailed, HerderError)` at line 992)
- Modify: `packages/llama/tests/test_gather.py`

**Interfaces:**
- Consumes: `RateLimited` (Task 2).
- Produces: no new API; `run_gather` now propagates `RateLimited` instead of degrading to a review flag.

- [ ] **Step 1: Write the failing test**

Append to `packages/llama/tests/test_gather.py`. Follow whatever fixture that file already uses to drive `run_gather` down the `align_structure` fallback branch — the branch is reached when there is no usable jerrybase evidence and `result.coverage < structure_cfg.align_coverage_threshold`, with a non-None `align_provider`. Reuse the file's existing helpers rather than building a new fixture; if the file has no test that reaches this branch, the smallest honest test is a direct one on the fallback's provider seam.

The test must assert:

```python
    with pytest.raises(RateLimited):
        run_gather(...)          # the same call the neighbouring tests make
```

and, critically, that no `low-confidence structure alignment` flag was written — the defect is not merely that the exception is eaten, it is that a wrong flag is persisted in its place.

Add `from herder.limits import RateLimited` to the imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_gather.py -q -k rate_limit`
Expected: FAIL — the exception is caught by `except (TaskFailed, HerderError)`, logged, and `low-confidence structure alignment` is appended instead.

- [ ] **Step 3: Write minimal implementation**

In `packages/llama/src/llama/stages/gather.py`, add `from herder.limits import RateLimited` to the imports, and add an explicit re-raise **above** the existing broad clause — do **not** narrow the broad clause, because the point is that the intent is legible at the call site:

```python
                except RateLimited:
                    # A usage window ran out. Degrading to a review flag here
                    # would write a `low-confidence structure alignment` the
                    # recording did not earn, and `should_run` means the
                    # resume never recomputes it - so the wrong flag would be
                    # permanent. Let it reach _execute, which pauses instead.
                    raise
                except (TaskFailed, HerderError) as err:
                    log.warning("align_structure failed: %s", err)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_gather.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_gather.py
git commit -m "fix(gather): let a usage-limit refusal propagate instead of flagging the show"
```

---

