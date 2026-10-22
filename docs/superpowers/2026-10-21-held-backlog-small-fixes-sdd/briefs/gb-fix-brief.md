# GATE B fix wave — brief (one implementer, one wave)

Context: the held-backlog small-fixes branch (spec docs/superpowers/specs/2026-10-21-held-backlog-small-fixes-design.md, slices B/C/D) passed every per-task review; the final whole-branch review asked for the fixes below. Scope is EXACTLY these five items, ruled by the owner's side (llama-db). Everything else stays deferred: do not touch it.

## 1. (Important) No tie-break when an operator venue override is set
- Where: packages/llama/src/llama/stages/gather.py:1405 `tie = venue_tie_break(candidate, sel)`; the override block at ~1470-1476 replaces only `venue`, so the tie-break's `sel_city` leaks through.
- Spec, slice B: "Arms that choose the venue themselves (enrichment, swap, 1c, 1d, operator override) are unaffected."
- Live case: jackiegreene-2010-05-29 ships 'angels camp, california' (selected recording's city) instead of the vote's 'Angels Camp, California'.
- Fix: `tie = venue_tie_break(candidate, sel) if overrides.venue is None else None` (`overrides` is in scope). A city-only override keeps the tie-broken venue (the operator did not choose the venue).
- Test FIRST and show it RED on HEAD: the jackiegreene shape — a tied grouping vote whose selected recording's own venue/city differ from the vote's (e.g. city differs only in case), plus `Overrides(venue="<operator venue>")` and no city override -> shipped venue is the override, shipped city is the VOTE's city, venue_source "override". Put it beside the existing slice B tie-break tests (find them: grep -n "venue_tie_break\|tie_break" packages/llama/tests/*.py). Optionally also pin the city-only override case (tie-broken venue + override city).

## 2. (Minor) Triage: a "changed by another command" refusal must not be a dead end
- Where: packages/llama/src/llama/cli.py, `_interactive_resolve`'s `except (LlamaError, HerderError): continue` arms. On `ShowChanged` triage loops back to the same show's prompt with the SAME session-long view, so every retry refuses again although the message says "run it again".
- Ruled behaviour: after a ShowChanged refusal, triage re-resolves the show, re-captures its view, re-prints it, and returns to its prompt, so a retry works. (E.g. `return _interactive_resolve(config, ia, ledger, entry)` or an equivalent loop restart — whatever matches the code; the re-capture must happen BEFORE the re-resolve, as T7's fix round established: capture view, then re-resolve.) Only ShowChanged takes this path; other errors keep today's behaviour (print error, same show's prompt). A show removed meanwhile keeps its current handling.
- Test: a changed show refuses once (another writer changes overrides.json/show.json between the view capture and the edit), then the retry on the re-printed prompt applies. Put it with the existing triage unit tests (packages/llama/tests/test_triage*.py; see how they stub `_redo_show_locked` and simulate a concurrent change).

## 3. (Minor, NARROW) Triage [m] and [i] print "updated" only after the unit succeeds
- Today `[m]` echoes "metadata override updated" (and `[i]` its routing/updated line) INSIDE the unit, so a rolled-back edit still prints "updated" before `error: …`.
- Fix: move those lines to after the unit exits successfully, as `fix` already does. No new "restored"/"left as it was" wording anywhere. A failed edit then prints only `error: …`.
- Test: tighten/extend the existing [m]/[i] failure tests to assert the "updated" text is ABSENT on failure and present on success.

## 4. (Minor) Track-number --exclude/--unexclude on a show with no show.json names the remedy
- Where: cli.py `_resolve_exclude_tokens` (~line 1497) says only "reference the file by name instead".
- Spec C4: the remaining refusals "now name the remedy, `llama redo <show> --from gather`". Reuse the existing suffix (`refuse_no_show_json` or whatever the code uses for the other no-show.json refusals) so the wording matches.
- Test: extend the existing no-show.json refusal test to assert the remedy text.

## 5. Docs only
- packages/llama/src/llama/stages/brief.py:121 `song_components` docstring says "`normalize_song`s each part"; it now goes through `_song_norm` (which folds curly apostrophes first). Correct it.
- show_unit docstring (packages/llama/src/llama/show_unit.py or wherever `show_unit` lives): limitation 3 omits the "cannot remove leftover snapshot" refusal; add it in one line.
- If CLAUDE.md describes any behaviour you change (e.g. triage's refusal/retry), keep it accurate with a minimal edit.

## Binding
- Global constraints: .superpowers/sdd/2026-10-21-held-backlog-small-fixes/global-constraints.md. `normalize_song`, `DEFAULT_ALIASES` and every do-not-retune constant stay byte-identical.
- Commit per item or per coherent pair, each with the test command run in the message and the trailer from global-constraints.md. Full suite once before the last commit: `./.venv/bin/python -m pytest -q` (was 4041 passed, 1 skipped, 8 deselected).
