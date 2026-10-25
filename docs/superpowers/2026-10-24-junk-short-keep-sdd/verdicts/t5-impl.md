# Task 5 handback (t5-impl): triage writer rules and numbered display

Status: DONE
Commit: see `git log -1` on held-backlog-junk-filter (feat(triage): legacy, staleness and keyed-exclusion refusals; numbers in the metadata line)
Tests: `./.venv/bin/python -m pytest -q` -> 4936 passed, 1 skipped, 8 deselected (73 s; the 4 xfails are gone). Baseline 4922 + 4 converted xfails + 10 new cases.

## Implemented (cli.py)
- `_interactive_resolve`: after the held check, `_legacy_message` -> `error: <msg>` and return (legacy or mixed text) before the prompt; walkthrough proceeds to next show.
- `[e]`: `_keyed_files(entry.ws)` on the picked files; each hit prints `error: ` + `_exclusion_refusal(...)`, back to prompt, nothing written.
- `[m]`: prompts first; `_stale` only when the answers set a title or break by number (venue/city/date, a cleared title, kept dangling keys are not gated).
- `[t]`, `[u]`: `_stale` before their prompts (`[t]` before `_propose_and_confirm_titles`).
- New helper `_stale_in_triage`: None when no show.json; LlamaError (IAError included) becomes the refusal text, never "fresh".
- `_metadata_editor`: defaults render `N=Title` / `N` with N the show.json index (titles sorted by N, dangling after as `<file>=Title`; breaks keep stored order, dangling as `<file>`). Typed input: digits = numbers; a non-digit key is accepted only if it is a stored dangling key (kept as given); other non-numeric input keeps the old error.
- `_edit_overrides.to_file` passes a non-digit string through as a filename (so a kept dangling key is written back).
- `_refuse_legacy` docstring reworded to be accurate (fix only; triage uses `_legacy_message`).

## TDD
RED (before implementation, 8 failed / 87 passed): legacy skip, mixed refusal, metadata line numbers, dangling render, two stale-[m] cases, stale [t]/[u], keyed exclusion. Passing already as pins (stated): venue edit not gated, `test_show_prints_the_stored_mapping`, and the 4 converted ex-xfail tests (they passed once converted: they only needed fixture shape/filename expectations, since the display change is not needed for them).
GREEN after implementation: 4 failures, all mine/fixture (below), then 95 passed, full suite green.

## Dry run (tests failing after implementation, before editing)
- test_triage_offers_u_only_when_every_track_is_unresolved, test_triage_u_confirmed_but_still_held_says_still_held, test_a_failed_untitled_resolution_restores_and_returns_to_the_prompt -> spec 4.2 staleness ([u] runs `_stale`; hand-built 1-track show.json is not gather's list) -> use `_gd73_show` / `_all_unresolved_show` (gd73 real gather, IAClient stubbed).
- test_triage_u_declined_writes_nothing_and_returns_to_the_prompt -> did NOT fail but was a FALSE PASS (stale refusal + un-stubbed IAClient, `continue` happened to satisfy its assertions) -> converted to `_all_unresolved_show` likewise.
- My new dangling test: expected order was wrong (breaks keep stored order) -> test fixed.
- Converted the 4 Task-3 xfails (removed marks): metadata_action (gd73 6-track show, `3,5` breaks, expects filename keys), metadata_empty_input (same), suggest_titles_resolution (ANCHORED_GAPS mapped to show.json filenames), sibling_arm (names[0], names[8]).
No unexplained failure. Network check: full suite 73 s (no archive.org stall).

## Files
packages/llama/src/llama/cli.py, packages/llama/tests/test_triage.py, packages/llama/tests/test_show_cmd.py.

## Decisions
1. `[m]` staleness gate fires only on numeric titles/breaks typed; a pure clear or kept-dangling edit is ungated (matches fix's --clear-* rule).
2. A typed non-digit title/break key is accepted only if it is a currently stored dangling key; any other stays the old parse error (typo protection).
3. `[m]` edited-titles path clears all stored titles then rewrites the answer (existing behaviour), so a dangling entry omitted from the answer is deleted (clears it without hand editing).
4. Legacy check sits after the held check, so non-held shows listed by a broader selector are not spuriously refused.
5. Multiple keyed hits in `[e]` each print their line.
6. Exclusion/stale errors go to stderr via `typer.echo(err=True)`, like the other triage errors.

## Concerns
- `[v]` and `[o]` are also refused for legacy files (whole show, per "every triage edit").
- `_stale` is not run for `[i]`/`[e]` (not positional).
- `test_show_prints_the_stored_mapping` is a pin: `llama show` already printed stored values unchanged.
