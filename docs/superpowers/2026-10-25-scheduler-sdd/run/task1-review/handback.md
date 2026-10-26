# task1-review: Task 1 (tolerant plan rows), 02b6d49..4fa87a7

### Spec Compliance
- ✅ `PlanRow` has every brief field with phase-1-safe defaults, and `extra` is `compare=False` and wrapped in `MappingProxyType` (layout.py:34-49).
- ✅ `from_json` splits known and unknown keys via `fields()`, turns `bends` into a tuple and `names` into 2-tuples, and raises TypeError on a bad shape (layout.py:70-85). `to_json` is hand-written, writes tuples as lists, adds `extra` after the known fields (known fields win), and no longer uses `asdict` (layout.py:55-68).
- ✅ `_parse_row` rejects a `kind` that is not a non-empty string (planner.py:153-154). The phase-1 checks are unchanged. A TypeError from `from_json` is still turned into a PlanError by `read_plan`'s `except (ValueError, TypeError)`; I checked planner.py:115-131.
- ✅ All three downstream skips are in place. `build_timeline` skips non-show rows (site.py:46). `_publish_site` skips them before it calls `analysis_for` (publish.py:244). `row_analysis` returns None before the cache lookup (service.py:84).
- ✅ The runbook gets a "Rolling transmitter back" subsection that names commits rather than task numbers, says never to truncate the plan by hand, and covers removing `[interstitials]` (docs/playout-setup.md:427-431).
- ✅ All the tests the brief lists are present.
- ⚠️ I could not verify the hugo Python 3.11 / Debian-12 gate from the diff. I saw no 3.12-only syntax.

### Strengths
- `to_json` and `from_json` are clean and symmetric. The comment about the collision rule is accurate. An input key literally named `"extra"` is handled correctly: it goes into `extra` with no duplicate-kwarg crash.
- The `row_analysis` test is not vacuous. It first proves the same cached key returns an analysis for a show row, then that it returns None for an interstitial row. A scratch-copy mutant confirmed this: with the guard removed, the test fails.
- The site test is also pinned. With the `build_timeline` guard removed, it fails with `['show-a', 'show-b'] == ['show-a']`.
- `cut_for_recovery`'s `replace()` still works. `__post_init__` re-wraps `dict(proxy)`, and nothing in src calls `asdict` or `deepcopy` on a PlanRow. I grepped src for both.

### Issues

#### Critical
None.

#### Important
1. **The publish test does not test its guard** (test_publish.py:481-494).
   - **Evidence:** In a scratch copy (`git archive`, run with PYTHONPATH shadowing and a control copy that passes), I removed `if r.kind != "show": continue` from `_publish_site`. `test_publish_site_never_asks_for_an_interstitial_analysis` still passes. The same test also passes with the `build_timeline` guard removed.
   - **Cause:** The interstitial row starts at segment 150, but the test only publishes segments 100..109. `_publish_site`'s window (`start_us < hi = start_us(last+1)`) and `build_timeline`'s window both drop the row whatever its `kind`, so `asked` never sees it.
   - **Why it matters:** The brief names this guard as one of the three skips that make this deploy-first commit safe, and nothing pins it.
   - **Fix:** Put the interstitial row inside the published window. For example, a show of a few segments at 100 and the interstitial at about 104, then publish 100..109. Assert that no row in `asked` has `kind != "show"` and that `timeline.json` lists only the show. Confirm the test fails with the guard removed.
   - **Note:** This test is plan-mandated, but the plan's own assertion only works if the row is inside the window. That is a defect in how the test was built, not a plan choice.

2. **The runbook understates the rollback hazard: this deploy cannot be rolled back on its own** (docs/playout-setup.md:429).
   - **The problem:** `to_json` now always writes every scheduler field (`kind`, `block`, `bends`, ...), even when it holds its default. Every `write_plan` rewrites the whole file (pipeline.py:179, 303). So once this build's first plan extension or render re-plan runs, every row in `plan.jsonl`, including phase-1 rows, carries keys that the previous build's `from_json` (`cls(**data)`) rejects with TypeError, which becomes PlanError. The previous build then wedges.
   - **Why the text misleads:** It says a pre-commit build "cannot read scheduler rows". An operator who deploys this commit alone, sees trouble, and rolls back to the current production build (`c3f6376`) would reasonably think that is safe because no scheduler rows exist yet. It is not. The operator checkpoint for this task is exactly that scenario.
   - **Fix (operator/controller choice):**
     - (a) Correct the text: a build from before this commit cannot read any plan this build has written, because every rewrite adds the new keys. Say that rolling back past it means stripping those keys by hand, or don't do it.
     - (b) Preferable: have `to_json` leave out scheduler fields that hold their default value. This keeps the deploy reversible until the scheduler writes its first non-default row. It deviates from the brief's "known fields via `dataclasses.fields`", so it needs a ruling. The round-trip tests still hold, because `from_json` defaults the missing keys.
   - **Note:** The inaccurate wording comes from the brief's Step 5 text, which the implementer reproduced faithfully. A stated source does not lower the severity.

#### Minor
1. **Scheduler fields are not type-checked on read** (planner.py:153; layout.py:76-84). Only `kind` is checked. `miss: "yes"`, `degraded: 1`, `bends: [1, 2]` and `names: [[1, 2]]` all load, and their types are accepted on write as well. This matches the brief, which only asks for `kind` plus tuple shapes. Later tasks that read `bends` and `names` as strings will meet unchecked data. Consider element-type checks when Task 7 or Task 11 first reads them.
2. **`extra` is only read-only one level deep** (layout.py:49, 67). A nested value in `extra` (e.g. `{"x": 1}`) is the same object as the one parsed from JSON, and `to_json` returns it unchanged, so a caller that mutates `to_json()` output mutates the row. Harmless today, because `write_plan` only serializes it.
3. **The `"extra"` key-name case is untested.** A plan key named `"extra"` round-trips correctly, as noted under Strengths, but no test pins it. One line would.
4. **`status_lines`' "on air" line would name an interstitial slug** (service.py:439). It is out of this task's three skips and only cosmetic, but it is another package-shaped reader to note for a later task.

### Assessment
**Task quality:** Needs fixes.
**Reasoning:** The core reader and writer and the three guards are correct, and two of the three guards are properly pinned. But the publish-site test passes even with its guard removed. And the runbook, which is the deliverable this deploy-first commit exists for, misstates when a rollback becomes unsafe: deploying this build alone already blocks rolling back to the previous one.

Evidence: scratch-copy mutants with control in the run log (`task1-review.log`); scratch removed afterwards.
