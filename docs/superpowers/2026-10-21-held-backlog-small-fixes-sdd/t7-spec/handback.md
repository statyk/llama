### Spec Compliance (SPEC role) — ✅ Spec compliant ; ⚠️ Cannot verify from diff: the C15 mutant is Task 8's to run, so whether it actually turns the test red was checked by reasoning, not by running it (see risk b).

### Strengths
- All seven triage edit paths in `cli._interactive_resolve` were checked: `[e]`, `[i]`, `[m]`, `[v]`, `[o]`, `[t]` and `[u]`.
  - Each runs its prompts first, with no lock held.
  - Each then does its write inside `show_unit(entry.ws, view)` (cli.py ~1964-1972), or for `[u]` inside `_untitled_resolution`'s own unit, which now uses the session view.
  - Nothing in `_interactive_resolve` still calls `_redo_show`. Its only remaining callers are redo and fix, at cli.py:3309 and 3403. No write to overrides happens outside a unit: `_metadata_editor` now returns the kwargs and writes nothing.
- The view is captured once per show turn, right after the path re-resolve and before `_print_show_entry`. The one-line comment the brief asks for is there. `[u]`'s old local `capture_view` was removed.
- The except clauses are `(LlamaError, HerderError)`, both the tail one and the one around `[u]`, and each `continue`s to the same show's prompt. Every error class the brief names falls under them: `IAError(LlamaError)` (ia_client.py:45), `ShowChanged(LlamaError)` (show_unit.py:46), `CatalogError(LlamaError)`, and `TaskFailed`/`RateLimited` under `HerderError`. `KeyboardInterrupt` is not caught, so it propagates after `show_unit` restores.
- The echo lines (the metadata "override updated" line and the unexclude routing note) are printed inside the unit after `edit()` and before the redo's writes, as the brief specifies. Their wording is unchanged.
- The CLAUDE.md sentence is present. It is reworded slightly, with the same content.
- All 8 tests in the brief are present and match it verbatim: `test_a_failed_triage_edit...`, `..._show_changed_meanwhile...`, `..._without_the_show_lock` (pin), `test_ctrl_c...`, `..._moves_on_to_the_next_show` (pin), `test_a_retry_after...`, `..._removed_before_its_turn...` and `test_a_failed_metadata_edit...`. The imports match too.
- The implementer reports 6 red and 2 pin passes before the change, which is what the brief expects. This covers the C5 items "a triage edit whose show changed between prompt and lock refuses and changes nothing" and "a triage edit that fails returns to the prompt".

Named-risk checks (one focused check each):
- (a) I grepped for `_redo_show(` in cli.py: the only hits are at 3309 and 3403, both outside triage. `_propose_and_confirm_titles` (around cli.py:2927) only confirms and writes nothing, so `[t]`'s write is the `edit` lambda. `_split_include_targets` only reads `show.json` during the prompt phase, as spec C1 step 1 allows.
- (b) The session view is set once (cli.py ~1842), and no branch captures it again. The C15 mutant would capture again after `_pick_excludes`. The picker in `test_a_triage_edit_whose_show_changed_meanwhile...` writes `overrides.json`, so the mutant's view would match and no refusal would happen. Both assertions would then fail: the refusal text would be missing, and `calls` would be `["gather"]`, not `[]`. I checked this by reasoning only.
- (c) The class hierarchy is confirmed above. `[u]` is wrapped in the same `try`.
- (d) For a removed show, `catalog.resolve_show`'s path form no longer passes `is_dir()`. The full path string then matches no slug, so `_resolve` raises `CatalogError("no show matches ...")`, a `LlamaError`. Triage prints `error: ...` and returns, moving on to the next show. Exact names take precedence in `_resolve`, so the re-resolve by slug inside the unit cannot land on a longer slug that merely contains this one.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- cli.py ~1970: the tail passes `_resolve_show(config, ledger, entry.slug)` to `_redo_show_locked`, where the brief's sketch passes `entry`. This keeps the old code's `fresh` re-resolve and matches `_untitled_resolution`. Exact names win, and it runs under the lock after the view check, so it is harmless. I note it only as a departure from the brief's literal text.
- test_triage.py, the removed-show test: it asserts only `"error: "`. It could also pin the slug or `no show matches`. This is coverage polish.
- No test fails `[u]`, `[e]`, `[i]` or `[t]` partway and asserts a return to the prompt. Only `[o]`, `[m]` and `[v]` (Ctrl-C) are exercised. The brief asks for no more, and all paths share the same tail, apart from `[u]`, which has its own `try`. This is coverage polish.

### Assessment
**Task quality:** Approved
**Reasoning:** Every Behaviour item in the brief and the triage parts of spec C1, C4 and C5 are implemented as specified, and every test the brief requires is present. All seven edit paths run inside one restoring unit against a view captured once per show turn. The two named error classes return to the prompt, and Ctrl-C ends the walkthrough after the restore.
