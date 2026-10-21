### Task 5: Honest pacing samples

**Implementer model: Sonnet** (one wrapper plus one condition, and the test-harness change specified below).

**Files:**
- Modify: `packages/llama/src/llama/pipeline.py`, `packages/llama/src/llama/cli.py:_execute` (first-pass loop only)
- Test: `packages/llama/tests/test_pace_loop.py`

**Interfaces:**
- Produces: `pipeline.count_llm_calls(providers: Mapping) -> tuple[Mapping, Callable[[], int]]` — returns a mapping that answers every key the original answers (including a `defaultdict`'s missing keys, lazily) with the value wrapped: a list (ladder) → list of wrappers, a single provider → wrapper, `None` → `None`. A wrapper's `complete`/`research` increment the shared counter **before** delegating (a call that raises still counts). The callable returns the count so far.
- `_execute`: `providers, llm_calls = count_llm_calls(make_providers(config))`. In the first-pass loop, take `calls_before = llm_calls()` right before `_process(entry)`; the boundary is recorded only if `ran and reading_before is not None and llm_calls() > calls_before` (spec §5); the after-show meter read sits inside that condition, so an LLM-free show takes none. The deferred pass is unchanged (records nothing).

- **Test harness change (`test_pace_loop._drive`):** its `make_providers` stub returns `collections.defaultdict(lambda: [FakeProvider(completes=["x"] * 50)])` (`herder.fake.FakeProvider`). `_drive` gains a keyword `llm: bool | Callable[[str], bool] = True`: its `_process_show` stub calls `providers["brief"][0].complete("x")` on the providers argument it receives (the counted wrapper) before `process(pid)` whenever `llm` is `True` or `llm(pid)` is true. The default keeps every existing test's behaviour: each show "called an LLM", so recorded boundaries and meter-read order are unchanged. The new download-only tests pass `llm=False`. For an LLM-free show the second meter read is skipped, which shifts scripted meter-read sequences; that is why the default is `llm=True`. Do not change existing assertions.

- [ ] **Step 1: Write failing tests** — `test_a_show_that_called_the_llm_records_a_boundary` (default `llm=True`); `test_a_download_only_resume_records_no_boundary` (`llm=False`; stub returns a package path → `pacing-state.json` unchanged); `test_an_already_packaged_show_records_no_boundary` (`llm=False`); `test_count_llm_calls_wraps_defaultdict_and_ladders` (unit test of the wrapper, including a raising fake counted once).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**, including the `_drive` change above; existing tests are not edited.
- [ ] **Step 4: Run** `./.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `fix(pacing): record a show boundary only when the show called an LLM`.

---

