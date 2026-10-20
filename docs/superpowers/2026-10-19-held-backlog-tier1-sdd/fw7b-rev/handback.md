VERDICT: APPROVED

fw7b-rev: review of c255ca7..cd9a0b6 (b30bed5, 17d3ba9, 0fead4d, cd9a0b6). Read-only; snapshot of cd9a0b6 via git archive, shadowing proven (llama.__file__ under the snapshot).

## Spec compliance (fw7b-brief.md)
| item | status | where |
|---|---|---|
| A1 fw6 2d clause (regex verbatim, once, note text, 7-Up, 1.02/1-002) | ✅ | CLAUDE.md:526-530; regex = titles.py:211, note = gather.py:1143 |
| A1 fw5 comma clause | ✅ | CLAUDE.md:531-534; brief.py song_comma_components |
| A1 fw4 `of` lookahead clause | ✅ | CLAUDE.md:535-537; brief.py `(?![^\S\n]+of\b)` in both regexes |
| A2 structure-change refusal, downloads, fw3 sentence re-wrapped | ✅ (wrap: see Minor 4) | CLAUDE.md:121-128 |
| A3 `--untitled` clears encore_after | ✅ | CLAUDE.md:142; cli.py:1639 `clear_encore=True` |
| A4 pacing gate list form only | ✅ | CLAUDE.md:134-135; names form (cli.py:3217-3244) has no gate |
| A4 1c single-event only | ✅ | CLAUDE.md:513; gather.py:1420-1422 |
| A4 needs-LLM covers stored alignment "llm" | ✅ (placement: Minor 1) | CLAUDE.md:112-113; replay.py:328-329 |
| A4 README "up to two attempts" | ✅ (wording: Minor 2) | README.md:257; brief.py:299 `range(2)` |
| A4 "including", not "plus" | ✅ | CLAUDE.md:152; replay_holds.py:183-187 has all three lists |
| B5 `_guard_prose` docstring + test comment | ✅ | brief.py:213-214; test_stage_brief.py:399 |
| B6 vague-branch comment | ✅ | brief.py:239 |
| B7 test_titles "six" + `[-_]` | ✅ | test_titles.py:661 (odd list has 6 entries) |
| C8 untitled still-held pin (fix + triage) | ✅ | test_fix.py:779; test_triage.py:635 |
| C9 briefing.md-only drop pin | ✅ | test_reapply.py:1001 |
| C10 mid-file imports moved | ✅ | 8 modules changed; AST re-scan of all 20 branch-touched test files: none left |
| C10 cities_not_compatible both orders | ✅ | test_structure.py:2045 |
| C10 `_two_arms` keyword args | ❌ partial (Minor 3) | scripts/test_replay_holds.py:439 still `_two_arms(tmp_path, unknown, unknown)` |
| C10 logging restored in finally | ✅ | scripts/test_replay_holds.py:286-292 |
| D11 cli comment | ✅ | cli.py:3367-3369 |
| D12 README `--allow-structure-change` + structure list apply | ✅ | README.md:267-271 |
| D13 dry-run skip + test | ✅ | reapply.py:107-110, cli.py:3356-3357; test_reapply.py:940 |
Nothing extra changed. Do-not-retune grep over the diff: only import-line moves (`normalize_song`, `GD_SHORTHAND`) and an unchanged doc reference to `_ENUMERATED_MIN_COVERAGE`; no constant moved.

## Import-move check (orchestrator extra)
Not 22 modules: the implementer's script scanned 22, but imports actually moved in 8 (test_jerrybase, test_reapply, test_replay, test_siblings, test_stage_brief, test_stage_gather, test_structure, test_titles). For all 8 I imported the module at c255ca7 and at cd9a0b6 and compared every module global's binding (module/qualname): identical except the intended new tests and test_cities_not_compatible's body (fixture Path constants differ only by snapshot root). So no test imports a different object and no moved import shadows/is shadowed by a local def. No importorskip/env/monkeypatch-dependent placement; test_reapply's `sys.path.insert` (line 9) still precedes the moved imports.

## 0fead4d as code
Correct. Without the flag, both dry-run paths return `dry-run: skipped: structure changed`, briefing "none"; the list form prints `would: <slug> -> skipped: structure changed` and counts neither brief nor download (the cli guard is what stops the download count; reapply's "none" alone would not). With the flag it's unchanged. Apply path unchanged. The names form prints `reapplied: <slug> -> dry-run: skipped: structure changed` (no "would:", as for every names-form dry-run, and no re-run hint) and has no summary, so nothing is counted there.

## Findings
Critical: none. Important: none.
Minor:
1. CLAUDE.md:112-113 "vet from the stored `vetting.json` extraction (none, or a stored alignment of `"llm"`, = needs-llm ...)": this reads as if the alignment were a vetting.json property. It is the stored show.json `structure.alignment` (replay.py:328). Fix: move it to the gather clause, e.g. "gather LLM-free from the cache (a stored `"llm"` alignment = needs-llm)".
2. README.md:257 "its only LLM call: one task of up to two attempts" contradicts itself (two attempts can be two calls). Fix: "its only LLM work: one brief task of up to two attempts".
3. scripts/test_replay_holds.py:439 `_two_arms(tmp_path, unknown, unknown)` is still 3-positional, which item 10 covers. Fix: `mutate_cand=unknown, mutate_base=unknown`.
4. New or rewritten CLAUDE.md lines exceed the file's ~80-col wrap: 115, 134, 135, 142, 154, 513, 530, 535; also README:257. Fix: re-wrap.
5. CLAUDE.md:126-128: "the dry-run counts `downloads` ... and, without the flag, neither counts nor predicts such a show". Two problems: only the `--from-list` dry-run prints a summary, and the dry-run does predict the skip. Fix: "the list dry-run's summary counts downloads ...; without the flag it predicts `skipped: structure changed` and counts nothing for it".
6. The names-form dry-run of a structure-changed show has no test of its own. M4/M5 are caught only through the list-form test. Optional: one test asserting `reapplied: <slug> -> dry-run: skipped: structure changed`.
7. Nits: test_stage_brief.py imports `briefing_guard` twice (lines 3 and 11). The moved imports are appended unsorted (stdlib `json`/`pytest`/`inspect` after first-party), which the implementer disclosed. 0fead4d landed its code before its test (cd9a0b6), so 0fead4d alone is unpinned. The suite is green at both.

## Mutation spot-check (snapshot copies under my own MROOT, PYTHONPATH shadow proven per mutant, private PYTHONPYCACHEPREFIX, predictions logged before flipping)
| mutant | predicted test | caught by |
|---|---|---|
| M1 cli `_untitled_resolution`: held path returns "declined" | test_fix::test_untitled_confirmed_but_still_held_says_still_held_not_declined + test_triage::test_triage_u_confirmed_but_still_held_says_still_held | both predicted (2 failed) |
| M2 reapply.py drop `or ws.briefing_md.exists()` | test_reapply::test_a_held_outcome_with_only_a_stale_briefing_md_drops_it | predicted |
| M3 cli drop `and not predicted.startswith("skipped")` | test_reapply::test_dry_run_of_a_structure_changed_row_is_skipped_unless_allowed | predicted |
| M4 reapply.py dry-run skip disabled (`if False:`) | same | predicted |
| M5 (not listed; added) dry-run skip ignores the flag | same (second half) | predicted |

## Suite (snapshot cd9a0b6, shadowed)
3802 passed, 1 skipped, 8 deselected, 26 warnings in 138.70s
