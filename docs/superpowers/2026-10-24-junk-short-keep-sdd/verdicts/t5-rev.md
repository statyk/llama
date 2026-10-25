# Task 5 review (t5-rev), 904eeb5..cbe7591

### Spec Compliance

- ✅ Spec compliant. Checked against brief Interfaces and spec 4.1/4.2 (lines 295-357):
  - Legacy/mixed: `_interactive_resolve` prints `error: <_legacy_message>` and returns before any prompt, after the held check (cli.py:1992-1995); the walkthrough moves on. Test cli test_triage.py:804 (byte-identical file, PROMPT count 1, second show reached) and :821 (mixed text).
  - `[t]` and `[u]` run `_stale` before their prompts (cli.py:2099, :2120); test :879 patches `typer.confirm` and `_propose_and_confirm_titles` to raise, so it proves no prompt was reached.
  - `[m]` prompts first, gates only when the answer carries an int title key or an int break (cli.py:2069-2075); venue/city/date not gated (test :897 on the stale windsor fixture).
  - `[e]` refuses keyed files with `_exclusion_refusal`'s fixed text, `continue`, nothing written (cli.py:2036-2042; test :907).
  - Metadata line renders show.json numbers, dangling keys as filenames, and the unchanged default returns None before any write (cli.py:1862-1871, 1880-1884; tests :831, :844 assert byte-identical `overrides.json`).
  - `llama show` pin (test_show_cmd.py:553): text and `--json`, dangling keys included.
  - Four Task-3 xfail marks removed, tests converted with filename expectations.
- ⚠️ Cannot verify from diff: the orchestrator's run reports `26 warnings`; the implementer reports none. Check that matches the Task-0 baseline's warning count (global constraint: output should be pristine relative to baseline).

### Named-risk checks

1. `to_file` non-digit passthrough (cli.py:1501-1502). I checked every caller of `_edit_overrides` that reaches `to_file`. `fix` parses `--set-title` keys to `int` (cli.py:3227-3233), `--set-breaks` to `int`s (:3244-3250) and `--set-encore` to `int` (:3251-3256), refusing a non-digit first. A non-digit `--clear-title` goes through the separate `str(n)` pop branch (:1532), not `to_file`. The `--suggest-titles` picks are `dict[int, str]` (:3091). `[u]`'s `set_titles` uses `range` ints (:1945-1948). `[t]` uses the same picks. Result: no `fix` flag can now write an unvalidated filename key. The only string source is triage's editor, which admits a non-digit key only when it is a stored dangling key (:1891-1893, :1902-1906). CLEARED.
2. `[m]` default round-trip. An unchanged answer returns None at :1882-1884 (no write, no redo). An edited answer maps numbers only inside `_edit_overrides.to_file`, which reads the current `show.json`, and does so under `show_unit(view)`: a `show.json` changed since `capture_view` refuses. CLEARED.
3. Gate bypass. A non-int key can only be a stored dangling filename, written back as itself, so no answer can re-point a key without an int. Re-typing a numbered title in a different form (its filename) is a parse error, not a passthrough (:1893 `n in dangling_titles` is false). `clear_titles` holds stored filenames (popped as given). `set_breaks=[]` names no file. CLEARED.
4. Triage refusals. The stale, keyed and parse errors all `continue` to the same show's prompt. Legacy returns, so the walkthrough goes on to the next show. `_stale_in_triage` turns any LlamaError, IAError included (ia_client.py:45), into refusal text (cli.py:1962-1972). No new path raises `typer.Exit`. CLEARED.
5. Network isolation. `_gd73_show`/`_windsor_show` (test_fix.py:1140, :1163), `_all_unresolved_show` (:710) and `_staged_ymsb_show` (test_cli.py:328) all stub `cli.IAClient`. I checked every `m`/`t`/`u` triage input in test_triage.py. The `_held_show` (unstubbed) cases are blank-answer `[m]`, venue-only `[m]`, or `t` without the flag, and none of them reaches `_stale`. CLEARED.
- Global-constraint grep of the diff for the protected names: no hits.

### Strengths
- Dangling keys are accepted only when they are already stored. That keeps typo protection and allows no new unvalidated filename.
- `_stale_in_triage` fails closed: an archive error becomes a refusal, never "fresh".
- Tests assert byte-identity (`read_bytes`/`tree_bytes`) and that no prompt was reached (raising stubs), not just "no error". The implementer also caught and converted a false-passing `[u]` test (`test_triage_u_declined_...`, which used to pass only via a stale refusal and an unstubbed IAClient).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- cli.py:1483-1489: the `_edit_overrides` docstring still says the positional arguments take TRACK NUMBERS. It does not mention the new string passthrough in `to_file`, and the "dangling key only" validation lives solely in triage's caller. The shared writer's contract widened silently; add one sentence saying that callers are responsible for passing only stored keys as strings.
- cli.py:2069-2071: `bool(A) and any(...) or (B and any(...))` relies on `and`/`or` precedence. It is correct, but wrap the first conjunct in parentheses for readability.
- cli.py:1886-1906 (pre-existing split, now reachable for dangling keys): a dangling filename containing `,` or `=` cannot be kept through an edited `[m]` answer, because the parse refuses with "title overrides expects N=Title". This fails safe: nothing is written, and `fix --clear-title <file>` is the route.
- test_triage.py:907: the keyed-exclusion test covers only a `titles` key. A `set_breaks`/`encore_after` case would pin the `--clear-set-breaks`/`--clear-encore` flag text from triage (the helper is shared with `fix`, so this is coverage only).

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief clause is implemented and tested with byte-identity and no-prompt assertions. The five named risks check out against the code: no `fix` path can reach the new `to_file` passthrough, no `[m]` answer can re-point a key past the staleness gate, and refusals stay inside the walkthrough. The remaining items are docstring, readability and coverage polish.
