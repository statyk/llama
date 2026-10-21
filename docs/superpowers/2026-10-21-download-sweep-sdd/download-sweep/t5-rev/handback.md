# t5-rev: Task 5 review (1a83c15..e5150cc)

### Spec Compliance
- ✅ Spec compliant. `count_llm_calls` (pipeline.py:36-82) matches the brief's interface: it returns a lazy Mapping view, so a defaultdict's missing keys still answer (pipeline.py:62, `self._inner[key]`); a list or tuple becomes a list of wrappers, a single provider a wrapper, and `None` stays `None` (pipeline.py:63-67). The wrapper increments the counter before delegating (pipeline.py:43-49). `_execute` wraps `make_providers(config)` (cli.py:416), takes `calls_before` right before the locked `_process` (cli.py:626), and gates the boundary on `ran and reading_before is not None and llm_calls() > calls_before` with the after-show `_meter` read inside the condition (cli.py:640-659). The deferred pass is untouched (cli.py:660-683). The `_drive` harness change follows the brief: a FakeProvider defaultdict, an `llm=` keyword defaulting to True, and the stub calls `providers["brief"][0].complete("x")` on the providers it is handed. The four named tests exist. The only existing test edited is the sanctioned one. Both folded cleanups are present: the comment at cli.py:561 and the `startswith("download of ")` assertion in test_execute_records_kind_for_a_failed_show.
- ⚠️ Cannot verify from diff: the claimed full-suite result (3884 passed). I did not re-run the suite. No doubt arose that needed a focused run.

### Strengths
- The wiring is pinned end-to-end, not just the unit. `_drive`'s stub counts through the providers `_execute` passes in. If `_execute` passed the raw mapping, every existing boundary-expecting test plus the new LLM test would go red. And the `llm=True` default keeps the existing scripted meter sequences valid without editing them.
- The unit test covers a raising call counted once (count-before-delegate), defaultdict lazy keys, a `None` value, a single provider's `complete` and `research`, and ladder-to-list.
- `test_a_download_only_resume_records_no_boundary` also asserts that the after-show meter read is skipped (`reads == with_llm - 1`), which is the brief's "an LLM-free show takes none" clause.
- The new comment at cli.py:641-645 explains why the zero-delta sample is excluded, in the same terms as the deferred-show rationale.

### Named risks checked
1. **Consumers of the providers mapping or isinstance checks on providers.** I grepped `packages/*/src` for isinstance/type checks, `.get/.copy/.items/...`, mutation, `**providers` and `make_providers(`.
   - The only isinstance is herder `tasks._as_ladder` (tasks.py:51), which checks for list/tuple. The view returns a `list`, so ladder escalation (`ladder[min(attempt, ...)]`) is preserved element-for-element.
   - `process_show` uses `providers[...]` and `providers.get("align_structure")` (pipeline.py:147-162). `Mapping.get` serves the latter.
   - Nothing mutates or copies the mapping. Nothing probes provider capability with `hasattr`/`getattr`, so a wrapper always having `research` is harmless.
   - The other `make_providers` call sites (cli.py:735, 2317, 3229, 3289, 3778) are outside `_execute` and unwrapped, which is correct for this task's scope.
2. **LLM spend that bypasses the mapping, so a show that did spend records no boundary.** The only `provider_ladder` and `make_providers` constructions in llama src are in pipeline.py and cli.py. Every LLM stage in `process_show` takes its provider from the passed mapping (pipeline.py:147-162). Nothing is missed.
3. **The harness FakeProvider running out and being masked as a show failure.** `FakeProvider.complete` raises `AssertionError` when its queue is empty (fake.py:23). `_process` catches only `RateLimited` and `(TaskFailed, HerderError, IAError)` (cli.py:575, 585), so running out would fail loudly rather than be silently recorded. No test in test_pace_loop.py drives anywhere near 50 shows.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The `pacing-state.json` assertions prove nothing.** They are at test_pace_loop.py, in `test_a_download_only_resume_records_no_boundary` and `test_an_already_packaged_show_records_no_boundary` (`assert not (tmp_path / "pacing-state.json").exists()`). `_boundaries` monkeypatches `cli.pacing_state.record` to a list-append stub, so the file can never be written even when a boundary is recorded. The `llm=True` sibling would pass the same assertion. The load-bearing assertion is `recorded == []`, which is real. Fix: drop the file assertions, or let one test run the real `record` and assert the file is absent or unchanged. The brief's wording ("pacing-state.json unchanged") suggests the latter was intended.
2. **`test_an_already_packaged_show_records_no_boundary` duplicates the download-only test.** It uses the same stub, returns the same package path, and differs only in passing `llm` as a constant-False predicate. It exercises the callable branch of `llm` but no new behaviour. A mixed run would pin the per-show delta more sharply: for example `["a", "b"]` with `llm=lambda pid: pid == "a"` asserting exactly one boundary. That would catch a mutant that compares against a run-level baseline instead of the per-show `calls_before`.
3. **Mapping-view semantics differ from a bare defaultdict.** In `_CountedProviders` (pipeline.py:55-75), the inherited `Mapping.get` and `__contains__` route through `__getitem__`. On a defaultdict input they therefore create the key and return the factory value, where `defaultdict.get` returns `None` without inserting. Production `make_providers` returns a plain dict with every TASK_KEY, so there is no runtime effect. This is the brief-mandated "answer missing keys lazily" behaviour, and only test inputs see it. A docstring note would prevent surprise.
4. **`_CountedProvider.__getattr__` can recurse.** At pipeline.py:51-52 it reads `self._inner`. On an instance built without `__init__` (copy, pickle), that read recurses until `RecursionError`. Nothing in herder or llama src copies or pickles providers (grepped `deepcopy|copy.copy|pickle`: no hits). This is a nit. `object.__getattribute__(self, "_inner")` or a `__slots__` guard would close it.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief and spec §5 exactly. The boundary condition, its placement and the untouched deferred pass are all correct, and every consumer of the wrapped mapping stays compatible. The remaining findings are test-assertion polish: one vacuous file assertion and one duplicate test. Neither leaves the strict LLM-spend surface unpinned, because `recorded == []` and the read-count assertion carry it.
